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
  });

  const ControllerStatus.offline()
      : connection = ConnectionStateLabel.offline,
        activeTasks = 0,
        enabledPlugins = 0,
        policyProfile = 'Safe',
        version = 'Unknown',
        environment = 'Unavailable',
        executorEnabled = false;

  const ControllerStatus.connecting()
      : connection = ConnectionStateLabel.connecting,
        activeTasks = 0,
        enabledPlugins = 0,
        policyProfile = 'Safe',
        version = 'Checking',
        environment = 'Connecting',
        executorEnabled = false;

  const ControllerStatus.online({
    required int activeTasks,
    required int enabledPlugins,
    required String policyProfile,
    required String version,
    required String environment,
    required bool executorEnabled,
  }) : this(
          connection: ConnectionStateLabel.online,
          activeTasks: activeTasks,
          enabledPlugins: enabledPlugins,
          policyProfile: policyProfile,
          version: version,
          environment: environment,
          executorEnabled: executorEnabled,
        );

  final ConnectionStateLabel connection;
  final int activeTasks;
  final int enabledPlugins;
  final String policyProfile;
  final String version;
  final String environment;
  final bool executorEnabled;
}

class ControllerHealth {
  const ControllerHealth({
    required this.service,
    required this.version,
    required this.status,
    required this.environment,
    required this.executorEnabled,
  });

  factory ControllerHealth.fromJson(Map<String, dynamic> json) {
    return ControllerHealth(
      service: json['service'] as String,
      version: json['version'] as String,
      status: json['status'] as String,
      environment: json['environment'] as String,
      executorEnabled: json['executor_enabled'] as bool,
    );
  }

  final String service;
  final String version;
  final String status;
  final String environment;
  final bool executorEnabled;
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
  });

  factory PluginSummary.fromJson(Map<String, dynamic> json) {
    return PluginSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      version: json['version'] as String,
      description: json['description'] as String,
      enabled: json['enabled'] as bool,
    );
  }

  final String id;
  final String name;
  final String version;
  final String description;
  final bool enabled;
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
  final bool startEnabled;
  final String? startEndpoint;
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
