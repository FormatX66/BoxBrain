class ArchitectureManifestSummary {
  const ArchitectureManifestSummary({
    required this.version,
    required this.name,
    required this.interfaceName,
    required this.flow,
    required this.principles,
    required this.agents,
    required this.compatibilityNotes,
  });

  factory ArchitectureManifestSummary.fromJson(Map<String, dynamic> json) {
    return ArchitectureManifestSummary(
      version: json['version'] as String,
      name: json['name'] as String,
      interfaceName: json['interface'] as String,
      flow: (json['flow'] as List<dynamic>).cast<String>(),
      principles: (json['principles'] as List<dynamic>).cast<String>(),
      agents: (json['agents'] as List<dynamic>)
          .map(
            (item) => SystemAgentSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
      compatibilityNotes:
          (json['compatibility_notes'] as List<dynamic>).cast<String>(),
    );
  }

  final String version;
  final String name;
  final String interfaceName;
  final List<String> flow;
  final List<String> principles;
  final List<SystemAgentSummary> agents;
  final List<String> compatibilityNotes;
}

class SystemAgentSummary {
  const SystemAgentSummary({
    required this.id,
    required this.name,
    required this.mission,
    required this.responsibilities,
    required this.boundary,
    required this.maturity,
    required this.compatibilityComponents,
  });

  factory SystemAgentSummary.fromJson(Map<String, dynamic> json) {
    return SystemAgentSummary(
      id: json['id'] as String,
      name: json['name'] as String,
      mission: json['mission'] as String,
      responsibilities:
          (json['responsibilities'] as List<dynamic>).cast<String>(),
      boundary: json['boundary'] as String,
      maturity: json['maturity'] as String,
      compatibilityComponents:
          (json['compatibility_components'] as List<dynamic>).cast<String>(),
    );
  }

  final String id;
  final String name;
  final String mission;
  final List<String> responsibilities;
  final String boundary;
  final String maturity;
  final List<String> compatibilityComponents;
}

class FleetDashboardSummary {
  const FleetDashboardSummary({
    required this.architectureVersion,
    required this.machineCount,
    required this.readyCount,
    required this.provisioningCount,
    required this.activeRunCount,
    required this.machines,
  });

  factory FleetDashboardSummary.fromJson(Map<String, dynamic> json) {
    return FleetDashboardSummary(
      architectureVersion: json['architecture_version'] as String,
      machineCount: json['machine_count'] as int,
      readyCount: json['ready_count'] as int,
      provisioningCount: json['provisioning_count'] as int,
      activeRunCount: json['active_run_count'] as int,
      machines: (json['machines'] as List<dynamic>)
          .map(
            (item) => FleetMachineSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
    );
  }

  final String architectureVersion;
  final int machineCount;
  final int readyCount;
  final int provisioningCount;
  final int activeRunCount;
  final List<FleetMachineSummary> machines;
}

class FleetMachineSummary {
  const FleetMachineSummary({
    required this.id,
    required this.machineIdentity,
    required this.name,
    required this.kind,
    required this.status,
    required this.remoteTargetId,
    required this.capabilities,
    required this.notes,
    required this.createdAt,
    required this.updatedAt,
  });

  factory FleetMachineSummary.fromJson(Map<String, dynamic> json) {
    return FleetMachineSummary(
      id: json['id'] as String,
      machineIdentity: json['machine_identity'] as String,
      name: json['name'] as String,
      kind: json['kind'] as String,
      status: json['status'] as String,
      remoteTargetId: json['remote_target_id'] as String?,
      capabilities: (json['capabilities'] as List<dynamic>).cast<String>(),
      notes: json['notes'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String machineIdentity;
  final String name;
  final String kind;
  final String status;
  final String? remoteTargetId;
  final List<String> capabilities;
  final String? notes;
  final DateTime createdAt;
  final DateTime updatedAt;
}

class ProvisioningRunSummary {
  const ProvisioningRunSummary({
    required this.id,
    required this.machineId,
    required this.status,
    required this.currentStepId,
    required this.steps,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ProvisioningRunSummary.fromJson(Map<String, dynamic> json) {
    return ProvisioningRunSummary(
      id: json['id'] as String,
      machineId: json['machine_id'] as String,
      status: json['status'] as String,
      currentStepId: json['current_step_id'] as String?,
      steps: (json['steps'] as List<dynamic>)
          .map(
            (item) => ProvisioningStepSummary.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  final String id;
  final String machineId;
  final String status;
  final String? currentStepId;
  final List<ProvisioningStepSummary> steps;
  final DateTime createdAt;
  final DateTime updatedAt;
}

class ProvisioningStepSummary {
  const ProvisioningStepSummary({
    required this.id,
    required this.position,
    required this.title,
    required this.instructions,
    required this.mode,
    required this.status,
    required this.note,
    required this.completedAt,
  });

  factory ProvisioningStepSummary.fromJson(Map<String, dynamic> json) {
    return ProvisioningStepSummary(
      id: json['id'] as String,
      position: json['position'] as int,
      title: json['title'] as String,
      instructions: json['instructions'] as String,
      mode: json['mode'] as String,
      status: json['status'] as String,
      note: json['note'] as String?,
      completedAt: json['completed_at'] == null
          ? null
          : DateTime.parse(json['completed_at'] as String),
    );
  }

  final String id;
  final int position;
  final String title;
  final String instructions;
  final String mode;
  final String status;
  final String? note;
  final DateTime? completedAt;
}
