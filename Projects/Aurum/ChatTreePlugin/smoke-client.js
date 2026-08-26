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
  requireInvariant(names.has("publish_live_state"), "cross-chat live-state publisher missing");
  requireInvariant(names.has("read_live_state"), "cross-chat live-state consumer missing");
  requireInvariant(names.has("show_chat_tree"), "Chat Tree display tool missing");
  requireInvariant(names.has("plan_chat_branch_consolidation"), "consolidation planner missing");
  requireInvariant(names.has("consolidate_chat_branch"), "consolidation action missing");
  requireInvariant(names.has("project_future_branch_status"), "human Future Branch tool missing");
  requireInvariant(names.has("plan_operational_futures"), "operational Future Branch tool missing");
  const listedByName = new Map((listed.tools ?? []).map((tool) => [tool.name, tool]));
  requireInvariant(listedByName.get("plan_chat_branch_consolidation")?.annotations?.readOnlyHint === true, "consolidation planner is not read-only");
  requireInvariant(listedByName.get("consolidate_chat_branch")?.annotations?.destructiveHint === true, "consolidation action does not require destructive approval");

  const consolidationPlan = await client.callTool({
    name: "plan_chat_branch_consolidation",
    arguments: {},
  });
  requireInvariant(consolidationPlan.structuredContent?.consolidation?.side_effects_performed === false, "consolidation planner changed state");
  requireInvariant(consolidationPlan.structuredContent?.consolidation?.underlying_chat_history_supported === false, "plugin claimed ChatGPT history access");
  if (process.env.AURUM_CHAT_TREE_MUTATION_SMOKE === "1") {
    const candidate = consolidationPlan.structuredContent?.consolidation?.candidates?.[0];
    requireInvariant(candidate?.source_node_ids?.length >= 2, "mutation smoke fixture has no consolidation candidate");
    const consolidated = await client.callTool({
      name: "consolidate_chat_branch",
      arguments: {
        sourceNodeIds: candidate.source_node_ids,
        planToken: candidate.plan_token,
        newNodeId: "smoke-archive",
        title: "Smoke archive",
        summary: "Mutation smoke test archive",
      },
    });
    requireInvariant(consolidated.structuredContent?.consolidationResult?.archived_source_ids?.length === 2, "sources were not archived");
    requireInvariant(consolidated.structuredContent?.consolidationResult?.underlying_chat_history_archived === false, "plugin claimed ChatGPT history mutation");
  }

  const published = await client.callTool({
    name: "publish_live_state",
    arguments: {
      subjectId: "chat:plugin-smoke",
      subjectKind: "chat",
      status: "running_verified",
      currentAction: "Exercise the public-shaped MCP publisher",
      blocker: "Production deployment is outside this smoke test",
      evidence: ["test:Projects/Aurum/ChatTreePlugin/smoke-client.js"],
      nextAction: "Read the event through the MCP consumer",
      actor: "chat:plugin-smoke",
      source: "mcp-smoke-client",
      nodeId: "cross-chat-context-cache",
      eventId: "evt-chat-tree-plugin-live-sync-smoke",
    },
  });
  requireInvariant(published.structuredContent?.event_count === 1, "publisher did not append exactly one event");
  requireInvariant(published.structuredContent?.authority_granted === false, "publisher granted execution authority");

  const consumed = await client.callTool({
    name: "read_live_state",
    arguments: {
      subjectId: "chat:plugin-smoke",
      includeHistory: true,
    },
  });
  const live = consumed.structuredContent?.live_state?.subjects?.["chat:plugin-smoke"];
  requireInvariant(live?.status === "running_verified", "consumer did not read the published status");
  requireInvariant(live?.current_action === "Exercise the public-shaped MCP publisher", "current action did not round-trip");
  requireInvariant(live?.blocker === "Production deployment is outside this smoke test", "blocker did not round-trip");
  requireInvariant(live?.evidence?.[0] === "test:Projects/Aurum/ChatTreePlugin/smoke-client.js", "evidence did not round-trip");
  requireInvariant(live?.next_action === "Read the event through the MCP consumer", "next action did not round-trip");
  requireInvariant(live?.grants_execution_authority === false, "consumer state grants execution authority");
  requireInvariant(consumed.structuredContent?.chat_memory_used_as_source === false, "consumer used chat memory as truth");

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

  console.log("AURUM_CHAT_TREE_LIVE_SYNC_AND_FUTURE_BRANCH_MCP_OK");
} finally {
  await client.close();
}
