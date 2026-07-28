class ProcessingAgentSummary {
  const ProcessingAgentSummary({
    required this.id,
    required this.name,
    required this.character,
    required this.responsibility,
    required this.capabilities,
    required this.executionMode,
    required this.enabled,
  });

  factory ProcessingAgentSummary.fromJson(Map<String, dynamic> json) {
    return ProcessingAgentSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      character: json['character'] as String,
      responsibility: json['responsibility'] as String,
      capabilities: (json['capabilities'] as List<dynamic>).cast<String>(),
      executionMode: json['execution_mode'] as String,
      enabled: json['enabled'] as bool? ?? true,
    );
  }

  final String id;
  final String name;
  final String character;
  final String responsibility;
  final List<String> capabilities;
  final String executionMode;
  final bool enabled;
}

class ModelRuntimeSummary {
  const ModelRuntimeSummary({
    required this.enabled,
    required this.configured,
    required this.sdkAvailable,
    required this.ready,
    required this.model,
    required this.executionMode,
    required this.externalSideEffectsEnabled,
  });

  factory ModelRuntimeSummary.fromJson(Map<String, dynamic> json) {
    return ModelRuntimeSummary(
      enabled: json['enabled'] as bool,
      configured: json['configured'] as bool,
      sdkAvailable: json['sdk_available'] as bool,
      ready: json['ready'] as bool,
      model: json['model'] as String,
      executionMode: json['execution_mode'] as String,
      externalSideEffectsEnabled: json['external_side_effects_enabled'] as bool,
    );
  }

  final bool enabled;
  final bool configured;
  final bool sdkAvailable;
  final bool ready;
  final String model;
  final String executionMode;
  final bool externalSideEffectsEnabled;
}

class AgentWorkspaceSummary {
  const AgentWorkspaceSummary({
    required this.projectCount,
    required this.memoryCount,
    required this.openTaskCount,
    required this.completedTaskCount,
    required this.processingRunCount,
    required this.estimatedTokens,
    required this.providerTokensUsed,
  });

  factory AgentWorkspaceSummary.fromJson(Map<String, dynamic> json) {
    return AgentWorkspaceSummary(
      projectCount: json['project_count'] as int,
      memoryCount: json['memory_count'] as int,
      openTaskCount: json['open_task_count'] as int,
      completedTaskCount: json['completed_task_count'] as int,
      processingRunCount: json['processing_run_count'] as int,
      estimatedTokens: json['estimated_tokens'] as int,
      providerTokensUsed: json['provider_tokens_used'] as int,
    );
  }

  final int projectCount;
  final int memoryCount;
  final int openTaskCount;
  final int completedTaskCount;
  final int processingRunCount;
  final int estimatedTokens;
  final int providerTokensUsed;
}

class AgentTaskSummary {
  const AgentTaskSummary({
    required this.id,
    required this.project,
    required this.title,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  factory AgentTaskSummary.fromJson(Map<String, dynamic> json) {
    return AgentTaskSummary(
      id: json['id'] as String,
      project: json['project'] as String,
      title: json['title'] as String,
      status: json['status'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String project;
  final String title;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;
}

class ProcessingStepSummary {
  const ProcessingStepSummary({
    required this.agentId,
    required this.status,
    required this.summary,
  });

  factory ProcessingStepSummary.fromJson(Map<String, dynamic> json) {
    return ProcessingStepSummary(
      agentId: json['agent_id'] as String,
      status: json['status'] as String,
      summary: json['summary'] as String,
    );
  }

  final String agentId;
  final String status;
  final String summary;
}

class LocalProcessingRunSummary {
  const LocalProcessingRunSummary({
    required this.id,
    required this.project,
    required this.intent,
    required this.status,
    required this.normalizedInput,
    required this.steps,
  });

  factory LocalProcessingRunSummary.fromJson(Map<String, dynamic> json) {
    return LocalProcessingRunSummary(
      id: json['id'] as String,
      project: json['project'] as String,
      intent: json['intent'] as String,
      status: json['status'] as String,
      normalizedInput: json['normalized_input'] as String,
      steps: (json['steps'] as List<dynamic>)
          .map(
            (item) => ProcessingStepSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
    );
  }

  final String id;
  final String project;
  final String intent;
  final String status;
  final String normalizedInput;
  final List<ProcessingStepSummary> steps;
}

class ModelPlanSummary {
  const ModelPlanSummary({
    required this.summary,
    required this.decisions,
    required this.tasks,
    required this.specialistHandoffs,
    required this.riskFlags,
    required this.requiresApproval,
  });

  factory ModelPlanSummary.fromJson(Map<String, dynamic> json) {
    return ModelPlanSummary(
      summary: json['summary'] as String,
      decisions: (json['decisions'] as List<dynamic>).cast<String>(),
      tasks: (json['tasks'] as List<dynamic>).cast<String>(),
      specialistHandoffs:
          (json['specialist_handoffs'] as List<dynamic>).cast<String>(),
      riskFlags: (json['risk_flags'] as List<dynamic>).cast<String>(),
      requiresApproval: json['requires_approval'] as bool,
    );
  }

  final String summary;
  final List<String> decisions;
  final List<String> tasks;
  final List<String> specialistHandoffs;
  final List<String> riskFlags;
  final bool requiresApproval;
}

class ProviderUsageSummary {
  const ProviderUsageSummary({
    required this.requests,
    required this.inputTokens,
    required this.outputTokens,
    required this.totalTokens,
  });

  factory ProviderUsageSummary.fromJson(Map<String, dynamic> json) {
    return ProviderUsageSummary(
      requests: json['requests'] as int,
      inputTokens: json['input_tokens'] as int,
      outputTokens: json['output_tokens'] as int,
      totalTokens: json['total_tokens'] as int,
    );
  }

  final int requests;
  final int inputTokens;
  final int outputTokens;
  final int totalTokens;
}

class ProcessingSubmissionResult {
  const ProcessingSubmissionResult({
    required this.localRun,
    this.plan,
    this.model,
    this.providerUsage,
  });

  factory ProcessingSubmissionResult.fromLocalJson(
    Map<String, dynamic> json,
  ) {
    return ProcessingSubmissionResult(
      localRun: LocalProcessingRunSummary.fromJson(json),
    );
  }

  factory ProcessingSubmissionResult.fromModelJson(
    Map<String, dynamic> json,
  ) {
    return ProcessingSubmissionResult(
      localRun: LocalProcessingRunSummary.fromJson(
        json['local_run'] as Map<String, dynamic>,
      ),
      plan: ModelPlanSummary.fromJson(
        json['plan'] as Map<String, dynamic>,
      ),
      model: json['model'] as String,
      providerUsage: ProviderUsageSummary.fromJson(
        json['usage'] as Map<String, dynamic>,
      ),
    );
  }

  final LocalProcessingRunSummary localRun;
  final ModelPlanSummary? plan;
  final String? model;
  final ProviderUsageSummary? providerUsage;

  bool get usedModel => plan != null;
}

class ChatOrganizerSummary {
  const ChatOrganizerSummary({
    required this.totalChatCount,
    required this.sourceProjectCount,
    required this.unassignedCount,
    required this.suggestedMoveCount,
    required this.pinnedCount,
    required this.lastSyncAt,
    required this.buckets,
    required this.recentChats,
  });

  factory ChatOrganizerSummary.fromJson(Map<String, dynamic> json) {
    return ChatOrganizerSummary(
      totalChatCount: json['total_chat_count'] as int,
      sourceProjectCount: json['source_project_count'] as int,
      unassignedCount: json['unassigned_count'] as int,
      suggestedMoveCount: json['suggested_move_count'] as int,
      pinnedCount: json['pinned_count'] as int,
      lastSyncAt: json['last_sync_at'] == null
          ? null
          : DateTime.parse(json['last_sync_at'] as String),
      buckets: (json['buckets'] as List<dynamic>)
          .map(
            (item) => ChatProjectBucketSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
      recentChats: (json['recent_chats'] as List<dynamic>)
          .map(
            (item) => OrganizedChatSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
    );
  }

  final int totalChatCount;
  final int sourceProjectCount;
  final int unassignedCount;
  final int suggestedMoveCount;
  final int pinnedCount;
  final DateTime? lastSyncAt;
  final List<ChatProjectBucketSummary> buckets;
  final List<OrganizedChatSummary> recentChats;
}

class ChatProjectBucketSummary {
  const ChatProjectBucketSummary({
    required this.name,
    required this.chatCount,
    required this.isExistingChatGptProject,
  });

  factory ChatProjectBucketSummary.fromJson(Map<String, dynamic> json) {
    return ChatProjectBucketSummary(
      name: json['name'] as String,
      chatCount: json['chat_count'] as int,
      isExistingChatGptProject: json['is_existing_chatgpt_project'] as bool,
    );
  }

  final String name;
  final int chatCount;
  final bool isExistingChatGptProject;
}

class OrganizedChatSummary {
  const OrganizedChatSummary({
    required this.externalId,
    required this.title,
    required this.currentProject,
    required this.suggestedProject,
    required this.classificationReason,
    required this.confidence,
    required this.pinnedIndex,
    required this.updatedAt,
  });

  factory OrganizedChatSummary.fromJson(Map<String, dynamic> json) {
    return OrganizedChatSummary(
      externalId: json['external_id'] as String,
      title: json['title'] as String,
      currentProject: json['current_project'] as String?,
      suggestedProject: json['suggested_project'] as String,
      classificationReason: json['classification_reason'] as String,
      confidence: json['confidence'] as String,
      pinnedIndex: json['pinned_index'] as int?,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String externalId;
  final String title;
  final String? currentProject;
  final String suggestedProject;
  final String classificationReason;
  final String confidence;
  final int? pinnedIndex;
  final DateTime updatedAt;
}

class ChatOrganizerImportSummary {
  const ChatOrganizerImportSummary({
    required this.id,
    required this.chatCount,
    required this.createdCount,
    required this.updatedCount,
    required this.unchangedCount,
    required this.suggestedMoveCount,
  });

  factory ChatOrganizerImportSummary.fromJson(Map<String, dynamic> json) {
    return ChatOrganizerImportSummary(
      id: json['id'] as String,
      chatCount: json['chat_count'] as int,
      createdCount: json['created_count'] as int,
      updatedCount: json['updated_count'] as int,
      unchangedCount: json['unchanged_count'] as int,
      suggestedMoveCount: json['suggested_move_count'] as int,
    );
  }

  final String id;
  final int chatCount;
  final int createdCount;
  final int updatedCount;
  final int unchangedCount;
  final int suggestedMoveCount;
}
