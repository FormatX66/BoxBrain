enum ConnectionStateLabel { offline, connecting, online }

class ControllerStatus {
  const ControllerStatus({
    required this.connection,
    required this.activeTasks,
    required this.enabledPlugins,
    required this.policyProfile,
    required this.version,
    required this.environment,
    required this.executorEnabled,
    this.authenticationRequired = false,
    this.eventStreamEnabled = false,
  });

  const ControllerStatus.offline()
      : connection = ConnectionStateLabel.offline,
        activeTasks = 0,
        enabledPlugins = 0,
        policyProfile = 'Safe',
        version = 'Unknown',
        environment = 'Unavailable',
        executorEnabled = false,
        authenticationRequired = false,
        eventStreamEnabled = false;

  const ControllerStatus.connecting()
      : connection = ConnectionStateLabel.connecting,
        activeTasks = 0,
        enabledPlugins = 0,
        policyProfile = 'Safe',
        version = 'Checking',
        environment = 'Connecting',
        executorEnabled = false,
        authenticationRequired = false,
        eventStreamEnabled = false;

  const ControllerStatus.online({
    required int activeTasks,
    required int enabledPlugins,
    required String policyProfile,
    required String version,
    required String environment,
    required bool executorEnabled,
    bool authenticationRequired = false,
    bool eventStreamEnabled = false,
  }) : this(
          connection: ConnectionStateLabel.online,
          activeTasks: activeTasks,
          enabledPlugins: enabledPlugins,
          policyProfile: policyProfile,
          version: version,
          environment: environment,
          executorEnabled: executorEnabled,
          authenticationRequired: authenticationRequired,
          eventStreamEnabled: eventStreamEnabled,
        );

  final ConnectionStateLabel connection;
  final int activeTasks;
  final int enabledPlugins;
  final String policyProfile;
  final String version;
  final String environment;
  final bool executorEnabled;
  final bool authenticationRequired;
  final bool eventStreamEnabled;
}

class ControllerHealth {
  const ControllerHealth({
    required this.service,
    required this.version,
    required this.status,
    required this.environment,
    required this.executorEnabled,
    this.authenticationRequired = false,
    this.eventStreamEnabled = false,
  });

  factory ControllerHealth.fromJson(Map<String, dynamic> json) {
    return ControllerHealth(
      service: json['service'] as String,
      version: json['version'] as String,
      status: json['status'] as String,
      environment: json['environment'] as String,
      executorEnabled: json['executor_enabled'] as bool,
      authenticationRequired: json['authentication_required'] as bool? ?? false,
      eventStreamEnabled: json['event_stream_enabled'] as bool? ?? false,
    );
  }

  final String service;
  final String version;
  final String status;
  final String environment;
  final bool executorEnabled;
  final bool authenticationRequired;
  final bool eventStreamEnabled;
}

class EmergencyStopState {
  const EmergencyStopState({
    required this.engaged,
    required this.reason,
    required this.generation,
    required this.changedAt,
  });

  const EmergencyStopState.unknown()
      : engaged = false,
        reason = null,
        generation = 0,
        changedAt = null;

  factory EmergencyStopState.fromJson(Map<String, dynamic> json) {
    return EmergencyStopState(
      engaged: json['engaged'] as bool,
      reason: json['reason'] as String?,
      generation: json['generation'] as int,
      changedAt: DateTime.parse(json['changed_at'] as String),
    );
  }

  final bool engaged;
  final String? reason;
  final int generation;
  final DateTime? changedAt;
}

class TaskSummary {
  const TaskSummary({
    required this.id,
    required this.goal,
    required this.targetId,
    required this.policyProfile,
    required this.status,
    required this.createdAt,
  });

  factory TaskSummary.fromJson(Map<String, dynamic> json) {
    return TaskSummary(
      id: json['id'] as String,
      goal: json['goal'] as String,
      targetId: json['target_id'] as String,
      policyProfile: json['policy_profile'] as String,
      status: json['status'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  final String id;
  final String goal;
  final String targetId;
  final String policyProfile;
  final String status;
  final DateTime createdAt;
}

class PolicySummary {
  const PolicySummary({
    required this.name,
    required this.description,
    required this.confirmationsRequired,
    required this.immutableAuditLog,
    required this.isolatedTargetRequired,
    required this.emergencyStopRequired,
  });

  factory PolicySummary.fromJson(Map<String, dynamic> json) {
    return PolicySummary(
      name: json['name'] as String,
      description: json['description'] as String,
      confirmationsRequired: json['confirmations_required'] as bool,
      immutableAuditLog: json['immutable_audit_log'] as bool,
      isolatedTargetRequired: json['isolated_target_required'] as bool,
      emergencyStopRequired: json['emergency_stop_required'] as bool,
    );
  }

  final String name;
  final String description;
  final bool confirmationsRequired;
  final bool immutableAuditLog;
  final bool isolatedTargetRequired;
  final bool emergencyStopRequired;
}

class PluginSummary {
  const PluginSummary({
    required this.id,
    required this.name,
    required this.version,
    required this.description,
    required this.enabled,
    required this.protocolVersion,
    required this.capabilities,
    required this.processBoundary,
    required this.targetId,
  });

  factory PluginSummary.fromJson(Map<String, dynamic> json) {
    return PluginSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      version: json['version'] as String,
      description: json['description'] as String,
      enabled: json['enabled'] as bool,
      protocolVersion: json['protocol_version'] as String,
      capabilities: (json['capabilities'] as List<dynamic>).cast<String>(),
      processBoundary: json['process_boundary'] as String,
      targetId: json['target_id'] as String?,
    );
  }

  final String id;
  final String name;
  final String version;
  final String description;
  final bool enabled;
  final String protocolVersion;
  final List<String> capabilities;
  final String processBoundary;
  final String? targetId;
}

class ObservationPolicySummary {
  const ObservationPolicySummary({
    required this.maxFrameWidth,
    required this.maxFrameBytes,
    required this.redactionRegionCount,
    required this.evidenceRetention,
    required this.maxRetainedFrames,
    required this.retentionMaxAgeSeconds,
  });

  factory ObservationPolicySummary.fromJson(Map<String, dynamic> json) {
    return ObservationPolicySummary(
      maxFrameWidth: json['max_frame_width'] as int,
      maxFrameBytes: json['max_frame_bytes'] as int,
      redactionRegionCount: json['redaction_region_count'] as int,
      evidenceRetention: json['evidence_retention'] as String,
      maxRetainedFrames: json['max_retained_frames'] as int,
      retentionMaxAgeSeconds: json['retention_max_age_seconds'] as int,
    );
  }

  final int maxFrameWidth;
  final int maxFrameBytes;
  final int redactionRegionCount;
  final String evidenceRetention;
  final int maxRetainedFrames;
  final int retentionMaxAgeSeconds;
}

class TargetSummary {
  const TargetSummary({
    required this.id,
    required this.name,
    required this.transport,
    required this.mode,
    required this.connected,
    required this.windowTitle,
    required this.frameEndpoint,
    required this.inputEnabled,
    required this.observerPluginId,
    required this.observerProcessBoundary,
    required this.observationStatus,
    required this.observationPolicy,
    required this.startEnabled,
    required this.startEndpoint,
  });

  factory TargetSummary.fromJson(Map<String, dynamic> json) {
    return TargetSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      transport: json['transport'] as String,
      mode: json['mode'] as String,
      connected: json['connected'] as bool,
      windowTitle: json['window_title'] as String,
      frameEndpoint: json['frame_endpoint'] as String?,
      inputEnabled: json['input_enabled'] as bool,
      observerPluginId: json['observer_plugin_id'] as String,
      observerProcessBoundary: json['observer_process_boundary'] as String,
      observationStatus: json['observation_status'] as String,
      observationPolicy: ObservationPolicySummary.fromJson(
        json['observation_policy'] as Map<String, dynamic>,
      ),
      startEnabled: json['start_enabled'] as bool,
      startEndpoint: json['start_endpoint'] as String?,
    );
  }

  final String id;
  final String name;
  final String transport;
  final String mode;
  final bool connected;
  final String windowTitle;
  final String? frameEndpoint;
  final bool inputEnabled;
  final String observerPluginId;
  final String observerProcessBoundary;
  final String observationStatus;
  final ObservationPolicySummary observationPolicy;
  final bool startEnabled;
  final String? startEndpoint;
}

class EdgeAgentSummary {
  const EdgeAgentSummary({
    required this.id,
    required this.name,
    required this.role,
    required this.transport,
    required this.mode,
    required this.connected,
    required this.version,
    required this.hostname,
    required this.targetCount,
    required this.recommendationCount,
    required this.networkInterface,
    required this.wifiCredentialAudit,
  });

  factory EdgeAgentSummary.fromJson(Map<String, dynamic> json) {
    return EdgeAgentSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      role: json['role'] as String,
      transport: json['transport'] as String,
      mode: json['mode'] as String,
      connected: json['connected'] as bool,
      version: json['version'] as String?,
      hostname: json['hostname'] as String?,
      targetCount: json['target_count'] as int,
      recommendationCount: json['recommendation_count'] as int,
      networkInterface: json['network_interface'] as String?,
      wifiCredentialAudit:
          json['wifi_credential_audit'] as String? ?? 'unavailable',
    );
  }

  final String id;
  final String name;
  final String role;
  final String transport;
  final String mode;
  final bool connected;
  final String? version;
  final String? hostname;
  final int targetCount;
  final int recommendationCount;
  final String? networkInterface;
  final String wifiCredentialAudit;
}

class RemoteTargetSummary {
  const RemoteTargetSummary({
    required this.id,
    required this.name,
    required this.transport,
    required this.host,
    required this.port,
    required this.username,
    required this.authorized,
    required this.builtIn,
    required this.status,
    required this.credentialMode,
    required this.capabilities,
    required this.lastCheckedAt,
    required this.createdAt,
  });

  factory RemoteTargetSummary.fromJson(Map<String, dynamic> json) {
    return RemoteTargetSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      transport: json['transport'] as String,
      host: json['host'] as String,
      port: json['port'] as int,
      username: json['username'] as String?,
      authorized: json['authorized'] as bool,
      builtIn: json['built_in'] as bool,
      status: json['status'] as String,
      credentialMode: json['credential_mode'] as String,
      capabilities: (json['capabilities'] as List<dynamic>).cast<String>(),
      lastCheckedAt: json['last_checked_at'] == null
          ? null
          : DateTime.parse(json['last_checked_at'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  final String id;
  final String name;
  final String transport;
  final String host;
  final int port;
  final String? username;
  final bool authorized;
  final bool builtIn;
  final String status;
  final String credentialMode;
  final List<String> capabilities;
  final DateTime? lastCheckedAt;
  final DateTime createdAt;
}

class RemoteTargetProbeSummary {
  const RemoteTargetProbeSummary({
    required this.targetId,
    required this.status,
    required this.resolvedAddress,
    required this.latencyMs,
    required this.message,
    required this.checkedAt,
  });

  factory RemoteTargetProbeSummary.fromJson(Map<String, dynamic> json) {
    return RemoteTargetProbeSummary(
      targetId: json['target_id'] as String,
      status: json['status'] as String,
      resolvedAddress: json['resolved_address'] as String?,
      latencyMs: json['latency_ms'] as int?,
      message: json['message'] as String,
      checkedAt: DateTime.parse(json['checked_at'] as String),
    );
  }

  final String targetId;
  final String status;
  final String? resolvedAddress;
  final int? latencyMs;
  final String message;
  final DateTime checkedAt;
}

class RemoteSessionSummary {
  const RemoteSessionSummary({
    required this.targetId,
    required this.status,
    required this.application,
    required this.message,
  });

  factory RemoteSessionSummary.fromJson(Map<String, dynamic> json) {
    return RemoteSessionSummary(
      targetId: json['target_id'] as String,
      status: json['status'] as String,
      application: json['application'] as String,
      message: json['message'] as String,
    );
  }

  final String targetId;
  final String status;
  final String application;
  final String message;
}

class DiagnosticPlanSummary {
  const DiagnosticPlanSummary({
    required this.action,
    required this.summary,
    required this.expectedEvidence,
    required this.riskNote,
  });

  factory DiagnosticPlanSummary.fromJson(Map<String, dynamic> json) {
    return DiagnosticPlanSummary(
      action: json['action'] as String,
      summary: json['summary'] as String,
      expectedEvidence: json['expected_evidence'] as String,
      riskNote: json['risk_note'] as String,
    );
  }

  final String action;
  final String summary;
  final String expectedEvidence;
  final String riskNote;
}

class DiagnosticProposalSummary {
  const DiagnosticProposalSummary({
    required this.id,
    required this.targetId,
    required this.targetName,
    required this.goal,
    required this.plan,
    required this.status,
    required this.model,
    required this.providerTokens,
    required this.requiresConfirmation,
    required this.createdAt,
    required this.expiresAt,
  });

  factory DiagnosticProposalSummary.fromJson(Map<String, dynamic> json) {
    final usage = json['usage'] as Map<String, dynamic>;
    return DiagnosticProposalSummary(
      id: json['id'] as String,
      targetId: json['target_id'] as String,
      targetName: json['target_name'] as String,
      goal: json['goal'] as String,
      plan: DiagnosticPlanSummary.fromJson(
        json['plan'] as Map<String, dynamic>,
      ),
      status: json['status'] as String,
      model: json['model'] as String,
      providerTokens: usage['total_tokens'] as int,
      requiresConfirmation: json['requires_confirmation'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
      expiresAt: DateTime.parse(json['expires_at'] as String),
    );
  }

  final String id;
  final String targetId;
  final String targetName;
  final String goal;
  final DiagnosticPlanSummary plan;
  final String status;
  final String model;
  final int providerTokens;
  final bool requiresConfirmation;
  final DateTime createdAt;
  final DateTime expiresAt;
}

class DiagnosticExecutionSummary {
  const DiagnosticExecutionSummary({
    required this.proposalId,
    required this.targetId,
    required this.action,
    required this.status,
    required this.exitCode,
    required this.output,
    required this.truncated,
    required this.durationMs,
    required this.executedAt,
  });

  factory DiagnosticExecutionSummary.fromJson(Map<String, dynamic> json) {
    return DiagnosticExecutionSummary(
      proposalId: json['proposal_id'] as String,
      targetId: json['target_id'] as String,
      action: json['action'] as String,
      status: json['status'] as String,
      exitCode: json['exit_code'] as int,
      output: json['output'] as String,
      truncated: json['truncated'] as bool,
      durationMs: json['duration_ms'] as int,
      executedAt: DateTime.parse(json['executed_at'] as String),
    );
  }

  final String proposalId;
  final String targetId;
  final String action;
  final String status;
  final int exitCode;
  final String output;
  final bool truncated;
  final int durationMs;
  final DateTime executedAt;
}

class AuditEventSummary {
  const AuditEventSummary({
    required this.sequence,
    required this.id,
    required this.eventType,
    required this.taskId,
    required this.targetId,
    required this.message,
    required this.details,
    required this.createdAt,
  });

  factory AuditEventSummary.fromJson(Map<String, dynamic> json) {
    return AuditEventSummary(
      sequence: json['sequence'] as int,
      id: json['id'] as String,
      eventType: json['event_type'] as String,
      taskId: json['task_id'] as String?,
      targetId: json['target_id'] as String?,
      message: json['message'] as String,
      details: json['details'] as Map<String, dynamic>,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  final int sequence;
  final String id;
  final String eventType;
  final String? taskId;
  final String? targetId;
  final String message;
  final Map<String, dynamic> details;
  final DateTime createdAt;
}
