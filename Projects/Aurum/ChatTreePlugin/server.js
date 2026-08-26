import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AURUM_ROOT = path.resolve(HERE, "..");
const BRIDGE = path.join(AURUM_ROOT, "Experiments", "chat_tree_bridge.py");
const WIDGET = readFileSync(path.join(HERE, "public", "chat-tree-widget.html"), "utf8");
const TEMPLATE_URI = "ui://aurum/chat-tree/v1.html";
const PYTHON = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");

function bridge(request) {
  const result = spawnSync(PYTHON, [BRIDGE], {
    cwd: AURUM_ROOT,
    input: JSON.stringify(request),
    encoding: "utf8",
    env: process.env,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(result.stderr?.trim() || result.stdout?.trim() || `bridge exited ${result.status}`);
  }
  const payload = JSON.parse(result.stdout);
  if (!payload.ok) throw new Error(payload.message || "Chat Tree bridge failed");
  return payload;
}

function snapshot(focusId) {
  const treeResponse = bridge({ command: "get_tree", ...(focusId ? { focus_id: focusId } : {}) });
  const stateResponse = bridge({ command: "get_state" });
  return {
    tree: treeResponse.tree,
    state: stateResponse.state,
    focusId: treeResponse.tree.focus_path?.at(-1) ?? treeResponse.tree.root_id,
  };
}

function reply(data, text) {
  return {
    structuredContent: data,
    content: text ? [{ type: "text", text }] : [],
  };
}

function createChatTreeServer() {
  const server = new McpServer({ name: "aurum-chat-tree-plugin", version: "0.1.0" });

  registerAppResource(server, "aurum-chat-tree-widget", TEMPLATE_URI, {}, async () => ({
    contents: [{
      uri: TEMPLATE_URI,
      mimeType: RESOURCE_MIME_TYPE,
      text: WIDGET,
      _meta: {
        ui: {
          prefersBorder: true,
          csp: { connectDomains: [], resourceDomains: [] },
        },
        "openai/widgetDescription": "Aurum Chat Tree navigator for focused, child, and sibling work lanes.",
      },
    }],
  }));

  registerAppTool(server, "show_chat_tree", {
    title: "Show Aurum Chat Tree",
    description: "Use this when the user wants to view or organize current Aurum conversation/process branches.",
    inputSchema: { focusId: z.string().optional() },
    _meta: {
      ui: { resourceUri: TEMPLATE_URI },
      "openai/outputTemplate": TEMPLATE_URI,
      "openai/toolInvocation/invoking": "Loading Chat Tree…",
      "openai/toolInvocation/invoked": "Chat Tree loaded.",
    },
  }, async ({ focusId }) => reply(snapshot(focusId), "Showing the current Aurum Chat Tree."));

  registerAppTool(server, "split_chat_topic", {
    title: "Split Aurum Chat Topic",
    description: "Use this when the objective changes enough to create a child subproblem or sibling topic in the durable Chat Tree.",
    inputSchema: {
      currentId: z.string().min(1),
      newNodeId: z.string().min(1),
      title: z.string().min(1),
      objective: z.string().min(1),
      relation: z.enum(["child", "sibling"]),
      concepts: z.array(z.string()).optional(),
      summary: z.string().optional(),
    },
    _meta: {
      ui: { resourceUri: TEMPLATE_URI },
      "openai/outputTemplate": TEMPLATE_URI,
      "openai/toolInvocation/invoking": "Splitting topic…",
      "openai/toolInvocation/invoked": "Topic split recorded.",
    },
  }, async (args) => {
    const routed = bridge({
      command: "route_topic",
      current_id: args.currentId,
      new_node_id: args.newNodeId,
      title: args.title,
      objective: args.objective,
      concepts: args.concepts ?? [],
      relation_hint: args.relation === "child" ? "subproblem" : "new",
      summary: args.summary ?? "",
      evidence_refs: [],
    });
    const data = snapshot(routed.focus_id);
    return reply({ ...data, route: routed }, `${args.title} is now a ${args.relation} Chat Tree branch.`);
  });

  return server;
}

const port = Number(process.env.PORT ?? 8788);
const MCP_PATH = "/mcp";
const httpServer = createServer(async (req, res) => {
  if (!req.url) return res.writeHead(400).end("Missing URL");
  const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "OPTIONS" && url.pathname === MCP_PATH) {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS, DELETE",
      "Access-Control-Allow-Headers": "content-type, mcp-session-id",
      "Access-Control-Expose-Headers": "Mcp-Session-Id",
    });
    return res.end();
  }

  if (req.method === "GET" && url.pathname === "/") {
    return res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({
      ok: true,
      service: "aurum-chat-tree-plugin",
      mcp: MCP_PATH,
    }));
  }

  if (url.pathname === MCP_PATH && new Set(["POST", "GET", "DELETE"]).has(req.method ?? "")) {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Expose-Headers", "Mcp-Session-Id");
    const server = createChatTreeServer();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    res.on("close", () => { transport.close(); server.close(); });
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res);
    } catch (error) {
      console.error(error);
      if (!res.headersSent) res.writeHead(500).end("Internal server error");
    }
    return;
  }

  res.writeHead(404).end("Not Found");
});

httpServer.listen(port, () => {
  console.log(`Aurum Chat Tree plugin listening on http://localhost:${port}${MCP_PATH}`);
});
