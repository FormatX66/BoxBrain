import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const endpoint = new URL(process.env.AURUM_CHAT_TREE_MCP ?? "http://127.0.0.1:8788/mcp");
const client = new Client({ name: "aurum-chat-tree-smoke", version: "0.1.0" });
const transport = new StreamableHTTPClientTransport(endpoint);

function requireInvariant(condition, message) {
  if (!condition) throw new Error(message);
}

try {
  await client.connect(transport);
  const listed = await client.listTools();
  const names = new Set((listed.tools ?? []).map((tool) => tool.name));
  requireInvariant(names.has("project_future_branch_status"), "human Future Branch tool missing");
  requireInvariant(names.has("plan_operational_futures"), "operational Future Branch tool missing");

  const human = await client.callTool({
    name: "project_future_branch_status",
    arguments: {
      verifiedState: "READY_TO_BOOT",
      lkg: "slot-a",
      likelyNext: [
        { state: "physical-hopper-boot-success", probability: 0.7 },
        { state: "boot-mixed-result", probability: 0.25 },
      ],
      blockers: ["physical-hopper-boot-proof"],
    },
  });
  requireInvariant(human.structuredContent?.authority_granted === false, "human projection granted authority");
  requireInvariant(human.structuredContent?.physical_proof_inferred === false, "human projection inferred physical proof");
  requireInvariant(
    human.structuredContent?.projection?.verified?.state === "READY_TO_BOOT",
    "verified state was not preserved",
  );
  requireInvariant(
    human.structuredContent?.projection?.likely_next?.[0]?.state === "physical-hopper-boot-success",
    "human futures were not ranked as expected",
  );

  const operational = await client.callTool({
    name: "plan_operational_futures",
    arguments: {
      verifiedState: "ci-green",
      candidates: [
        {
          name: "inspect-ci-logs",
          domain: "ci-build",
          probability: 0.8,
          impact: 0.8,
          human_time_saved: 2,
          preparation_leverage: 1,
          cost: 0.2,
          read_only: true,
        },
        {
          name: "publish-site",
          domain: "website-deployment",
          probability: 0.6,
          impact: 0.8,
          human_time_saved: 2,
          preparation_leverage: 0.8,
          cost: 0.4,
          external_side_effect: true,
          authorization_required: true,
          rollback_prepared: true,
        },
      ],
    },
  });
  requireInvariant(operational.structuredContent?.authority_granted === false, "operational plan granted authority");
  requireInvariant(operational.structuredContent?.plan?.external_action_allowed === false, "operational plan allowed external action");
  const branches = new Map((operational.structuredContent?.plan?.branches ?? []).map((branch) => [branch.name, branch]));
  requireInvariant(branches.get("inspect-ci-logs")?.disposition === "prepare", "safe read-only branch was not prepared");
  requireInvariant(branches.get("publish-site")?.disposition === "wait-boundary", "external effect did not stop at authority boundary");

  console.log("AURUM_CHAT_TREE_FUTURE_BRANCH_MCP_OK");
} finally {
  await client.close();
}
