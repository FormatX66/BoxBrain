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
import { handleFarmerToolCall } from "./farmer-actuator.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const AURUM_ROOT = path.resolve(HERE, "..");
const BRIDGE = path.join(AURUM_ROOT, "Experiments", "chat_tree_bridge.py");
const WIDGET = readFileSync(path.join(HERE, "public", "chat-tree-widget.html"), "utf8");
const TEMPLATE_URI = "ui://aurum/chat-tree/v5.html";
const PYTHON = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const STATUS = z.enum([
  "planned",
  "queued",
  "running_unverified",
  "running_verified",
  "waiting",
  "blocked",
  "succeeded",
  "failed",
  "no_change",
  "refused",
]);

function bridgeArguments() {
  const args = [BRIDGE];
  const overrides = [
    ["CHAT_TREE_TREE_PATH", "--tree"],
    ["CHAT_TREE_EVENTS_PATH", "--events"],
    ["CHAT_TREE_PROJECTION_PATH", "--projection"],
  ];
  for (const [variable, flag] of overrides) {
    if (process.env[variable]) args.push(flag, process.env[variable]);
  }
  return args;
}

function bridge(request) {
  const result = spawnSync(PYTHON, bridgeArguments(), {
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
  const consolidationResponse = bridge({ command: "plan_consolidation" });
  return {
    tree: treeResponse.tree,
    state: stateResponse.state,
    consolidation: consolidationResponse,
    focusId: treeResponse.tree.focus_path?.at(-1) ?? treeResponse.tree.root_id,
  };
}

function reply(data, text) {
  return {
    structuredContent: data,
    content: text ? [{ type: "text", text }] : [],
  };
}

function closeQuietly(resource) {
  try {
    const result = resource?.close?.();
    if (result && typeof result.catch === "function") result.catch(() => {});
  } catch {
    // Per-request/stateless cleanup must never terminate the long-lived HTTP listener.
  }
}

function createChatTreeServer() {
  const server = new McpServer({ name: "aurum-chat-tree-plugin", version: "0.3.0" });

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
        "openai/widgetDescription": "Aurum Chat Tree navigator with strict same-group/same-branch consolidation planning.",
      },
    }],
  }));

  registerAppTool(server, "show_chat_tree", {
    title: "Show Aurum Chat Tree",
    description: "Use this when the user wants to view, search, organize, or review consolidation candidates in current Aurum conversation/process branches.",
    inputSchema: { focusId: z.string().optional() },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    },
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
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
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

  server.registerTool("publish_live_state", {
    title: "Publish Aurum Cross-Chat Live State",
    description: "Append a chat/process status, current action, blocker, evidence, and next action to the evidence-backed shared-state bus. Verified runtime/success claims require evidence; the bus grants no execution authority.",
    inputSchema: {
      subjectId: z.string().min(1),
      status: STATUS,
      currentAction: z.string().min(1),
      blocker: z.string().min(1).nullable(),
      evidence: z.array(z.string().min(1)).max(64),
      nextAction: z.string().min(1),
      actor: z.string().min(1),
      source: z.string().min(1),
      subjectKind: z.string().min(1).optional(),
      nodeId: z.string().min(1).optional(),
      summary: z.string().optional(),
      dependencyIds: z.array(z.string().min(1)).max(64).optional(),
      confidence: z.number().min(0).max(1).optional(),
      authorityRef: z.string().min(1).optional(),
      eventId: z.string().min(1).optional(),
      payload: z.record(z.unknown()).optional(),
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
  }, async (args) => {
    const published = bridge({
      command: "publish_live_state",
      subject_id: args.subjectId,
      subject_kind: args.subjectKind ?? "chat",
      status: args.status,
      current_action: args.currentAction,
      blocker: args.blocker,
      evidence: args.evidence,
      next_action: args.nextAction,
      actor: args.actor,
      source: args.source,
      ...(args.nodeId ? { node_id: args.nodeId } : {}),
      summary: args.summary ?? "",
      dependency_ids: args.dependencyIds ?? [],
      ...(args.confidence === undefined ? {} : { confidence: args.confidence }),
      ...(args.authorityRef ? { authority_ref: args.authorityRef } : {}),
      ...(args.eventId ? { event_id: args.eventId } : {}),
      payload: args.payload ?? {},
    });
    return reply(published, "Live state appended to the evidence-backed bus; no execution authority was granted.");
  });

  server.registerTool("read_live_state", {
    title: "Read Aurum Cross-Chat Live State",
    description: "Read the newest evidence-backed status, current action, blocker, evidence, and next action from the shared-state bus instead of relying on chat memory.",
    inputSchema: {
      subjectId: z.string().min(1).optional(),
      nodeId: z.string().min(1).optional(),
      verifiedOnly: z.boolean().optional(),
      includeHistory: z.boolean().optional(),
      limit: z.number().int().min(1).max(500).optional(),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  }, async (args) => {
    const consumed = bridge({
      command: "read_live_state",
      ...(args.subjectId ? { subject_id: args.subjectId } : {}),
      ...(args.nodeId ? { node_id: args.nodeId } : {}),
      verified_only: args.verifiedOnly ?? false,
      include_history: args.includeHistory ?? false,
      limit: args.limit ?? 50,
    });
    return reply(consumed, "Read the newest matching state from the append-only shared-state bus.");
  });

  registerAppTool(server, "plan_chat_branch_consolidation", {
    title: "Plan Chat Branch Consolidation",
    description: "Find completed or failed Chat Tree nodes in the exact same parent group and branch lane. This is read-only and cannot archive conversations in ChatGPT history.",
    inputSchema: {
      parentId: z.string().min(1).optional(),
      laneId: z.string().min(1).optional(),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    },
    _meta: {
      ui: { resourceUri: TEMPLATE_URI },
      "openai/outputTemplate": TEMPLATE_URI,
      "openai/toolInvocation/invoking": "Checking branch archives…",
      "openai/toolInvocation/invoked": "Branch archive plan ready.",
    },
  }, async ({ parentId, laneId }) => {
    const planned = bridge({
      command: "plan_consolidation",
      ...(parentId ? { parent_id: parentId } : {}),
      ...(laneId ? { lane_id: laneId } : {}),
    });
    return reply(
      { ...snapshot(), consolidation: planned },
      planned.candidate_count
        ? `Found ${planned.candidate_count} exact same-group/same-branch consolidation candidate${planned.candidate_count === 1 ? "" : "s"}.`
        : "No exact same-group/same-branch consolidation candidates are ready.",
    );
  });

  registerAppTool(server, "consolidate_chat_branch", {
    title: "Consolidate and Archive Chat Tree Branch",
    description: "Apply one exact reviewed plan: create a provenance-preserving checkpoint and archive its completed/failed source nodes in the Aurum Chat Tree. This does not archive the underlying conversations in ChatGPT history.",
    inputSchema: {
      sourceNodeIds: z.array(z.string().min(1)).min(2).max(64),
      planToken: z.string().length(64),
      newNodeId: z.string().min(1),
      title: z.string().min(1),
      summary: z.string().optional(),
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: true,
      idempotentHint: false,
      openWorldHint: false,
    },
    _meta: {
      ui: { resourceUri: TEMPLATE_URI },
      "openai/outputTemplate": TEMPLATE_URI,
      "openai/toolInvocation/invoking": "Consolidating branch…",
      "openai/toolInvocation/invoked": "Chat Tree sources archived.",
    },
  }, async (args) => {
    const consolidated = bridge({
      command: "consolidate_branch",
      source_node_ids: args.sourceNodeIds,
      plan_token: args.planToken,
      new_node_id: args.newNodeId,
      title: args.title,
      summary: args.summary ?? "",
    });
    return reply(
      { ...snapshot(consolidated.focus_id), consolidationResult: consolidated },
      `Consolidated and archived ${consolidated.archived_source_ids.length} Chat Tree nodes. ChatGPT conversation history was not changed.`,
    );
  });

  server.registerTool("dispatch_farmer_objective", {
    title: "Dispatch Aurum Farmer Objective",
    description: "Dispatch one bounded Aurum Farmer objective into the verified GitHub event-driven completion controller. This tool never accepts shell commands, code, workflow names, repository names, tokens, URLs, or arbitrary execution payloads.",
    inputSchema: {
      objective_id: z.string().min(3).max(64).regex(/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/),
      objective: z.string().min(1).max(4000),
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
    },
  }, async (args) => {
    const dispatched = await handleFarmerToolCall("dispatch_farmer_objective", args);
    return reply(
      dispatched,
      dispatched.status === "dispatch_accepted"
        ? "Aurum Farmer accepted the objective and will continue through GitHub executor and verifier receipts."
        : "Aurum Farmer dispatch is machine-blocked; no human relay is required.",
    );
  });

  server.registerTool("project_future_branch_status", {
    title: "Project Aurum Future Branch Status",
    description: "Project likely next human/session states while keeping verified state, LKG, blockers, and authority visibly separate from speculation.",
    inputSchema: {
      verifiedState: z.string().min(1),
      lkg: z.string().nullable().optional(),
      likelyNext: z.array(z.object({
        state: z.string().min(1),
        probability: z.number().min(0).max(1),
      })).max(16),
      blockers: z.array(z.string()).optional(),
    },
  }, async (args) => {
    const projected = bridge({
      command: "project_human_futures",
      verified_state: args.verifiedState,
      lkg: args.lkg ?? null,
      likely_next: args.likelyNext,
      blockers: args.blockers ?? [],
    });
    return reply(projected, "Future Branch projection prepared without granting authority or physical proof.");
  });

  server.registerTool("plan_operational_futures", {
    title: "Plan Aurum Operational Futures",
    description: "Rank safe CI/build, website/deployment, and external-content preparation branches. External effects, trust broadening, and unchanged retry loops remain blocked.",
    inputSchema: {
      verifiedState: z.string().min(1),
      limit: z.number().int().min(1).max(16).optional(),
      candidates: z.array(z.object({
        name: z.string().min(1),
        domain: z.enum(["ci-build", "website-deployment", "external-content"]),
        probability: z.number().min(0).max(1),
        impact: z.number().min(0).max(1),
        human_time_saved: z.number().min(0),
        preparation_leverage: z.number().min(0),
        cost: z.number().min(0),
        evidence_freshness: z.number().min(0).max(1).optional(),
        read_only: z.boolean().optional(),
        reversible: z.boolean().optional(),
        external_side_effect: z.boolean().optional(),
        authorization_required: z.boolean().optional(),
        rollback_prepared: z.boolean().optional(),
        preserves_verified_state: z.boolean().optional(),
        unchanged_retry: z.boolean().optional(),
        retry_after_seconds: z.number().int().min(0).optional(),
        trust_broadening: z.boolean().optional(),
        alternate_authorized_route: z.boolean().optional(),
      })).max(32),
    },
  }, async (args) => {
    const planned = bridge({
      command: "plan_operational_futures",
      verified_state: args.verifiedState,
      limit: args.limit ?? 8,
      candidates: args.candidates,
    });
    return reply(planned, "Operational Future Branch plan prepared; no external action or authority was granted.");
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
    res.on("close", () => {
      closeQuietly(transport);
      closeQuietly(server);
    });
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
