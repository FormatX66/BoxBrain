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
