import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:boxbrain_ui/models/controller_status.dart';
import 'package:boxbrain_ui/models/fleet_models.dart';
import 'package:boxbrain_ui/screens/fleet_screen.dart';
import 'package:boxbrain_ui/services/controller_api.dart';

void main() {
  testWidgets('runs the operator-guided fleet provisioning workflow', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _FleetControllerApi();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: FleetScreen(api: api, active: true)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Fleet & provisioning'), findsOneWidget);
    expect(find.text('Architecture v1.0'), findsOneWidget);
    expect(find.text('Kali Pi USB-C'), findsOneWidget);
    expect(find.text('Orchestrator'), findsOneWidget);
    expect(find.text('System agent roster (12)'), findsOneWidget);

    await tester.tap(find.byKey(const Key('start-provisioning')));
    await tester.pumpAndSettle();

    expect(api.startCalls, 1);
    expect(find.text('Open Google account setup'), findsOneWidget);
    final complete = find.byKey(const Key('complete-provisioning-step'));
    await tester.ensureVisible(complete);
    await tester.tap(complete);
    await tester.pumpAndSettle();
    expect(find.text('Complete Open Google account setup?'), findsOneWidget);

    await tester.tap(find.text('Mark complete'));
    await tester.pumpAndSettle();

    expect(api.completeCalls, 1);
    expect(find.text('Complete CAPTCHA'), findsOneWidget);
  });
}

class _FleetControllerApi extends ControllerApi {
  _FleetControllerApi();

  int startCalls = 0;
  int completeCalls = 0;
  ProvisioningRunSummary? run;

  static final machine = FleetMachineSummary(
    id: 'machine-1',
    machineIdentity: 'BB-RPI-000000000001',
    name: 'Kali Pi USB-C',
    kind: 'raspberry-pi',
    status: 'detected',
    remoteTargetId: 'target-1',
    capabilities: const ['edge-diagnostics', 'interactive-shell'],
    notes: null,
    createdAt: DateTime.utc(2026, 7, 28),
    updatedAt: DateTime.utc(2026, 7, 28),
  );

  @override
  Future<ArchitectureManifestSummary> fetchArchitecture() async {
    return ArchitectureManifestSummary(
      version: '1.0',
      name: 'BoxBrain Master Architecture',
      interfaceName: 'Arkmatx Interface',
      flow: const [
        'Bruce (User)',
        'Arkmatx Interface',
        'BoxBrain (AI Orchestrator)',
        'Specialized Agents',
        'Brain Connect',
        'Authorized Machine',
      ],
      principles: const ['modular', 'versioned', 'testable'],
      agents: List.generate(
        12,
        (index) => SystemAgentSummary(
          id: index == 0 ? 'orchestrator' : 'agent-$index',
          name: index == 0 ? 'Orchestrator' : 'Agent $index',
          mission: 'Coordinate a bounded BoxBrain responsibility.',
          responsibilities: const ['plan', 'report'],
          boundary: 'planner',
          maturity: 'operational',
          compatibilityComponents: const [],
        ),
      ),
      compatibilityNotes: const [
        'The existing ten-agent processing crew remains unchanged.',
      ],
    );
  }

  @override
  Future<FleetDashboardSummary> fetchFleet() async {
    return FleetDashboardSummary(
      architectureVersion: '1.0',
      machineCount: 1,
      readyCount: 0,
      provisioningCount: run == null ? 0 : 1,
      activeRunCount: run == null ? 0 : 1,
      machines: [machine],
    );
  }

  @override
  Future<List<RemoteTargetSummary>> fetchRemoteTargets() async {
    return [
      RemoteTargetSummary(
        id: 'target-1',
        name: 'Kali Pi USB-C',
        transport: 'usb-c',
        host: '10.12.194.1',
        port: 22,
        username: 'kali',
        authorized: true,
        builtIn: true,
        status: 'online',
        credentialMode: 'dedicated-key',
        capabilities: const ['edge-diagnostics'],
        lastCheckedAt: DateTime.utc(2026, 7, 28),
        createdAt: DateTime.utc(2026, 7, 28),
      ),
    ];
  }

  @override
  Future<ProvisioningRunSummary?> fetchMachineProvisioning(
    String machineId,
  ) async {
    return run;
  }

  @override
  Future<ProvisioningRunSummary> startMachineProvisioning(
    String machineId,
  ) async {
    startCalls += 1;
    run = _run(current: 'open-google-signup');
    return run!;
  }

  @override
  Future<ProvisioningRunSummary> completeProvisioningStep({
    required String runId,
    required String stepId,
    String? note,
  }) async {
    completeCalls += 1;
    run = _run(current: 'complete-captcha', firstCompleted: true);
    return run!;
  }

  ProvisioningRunSummary _run({
    required String current,
    bool firstCompleted = false,
  }) {
    return ProvisioningRunSummary(
      id: 'run-1',
      machineId: machine.id,
      status: 'in_progress',
      currentStepId: current,
      steps: [
        ProvisioningStepSummary(
          id: 'open-google-signup',
          position: 4,
          title: 'Open Google account setup',
          instructions: 'Open setup in a user-controlled browser.',
          mode: 'external-guided',
          status: firstCompleted ? 'completed' : 'pending',
          note: firstCompleted ? 'Opened by operator.' : null,
          completedAt: firstCompleted ? DateTime.utc(2026, 7, 28) : null,
        ),
        const ProvisioningStepSummary(
          id: 'complete-captcha',
          position: 5,
          title: 'Complete CAPTCHA',
          instructions: 'The operator completes the challenge.',
          mode: 'operator',
          status: 'pending',
          note: null,
          completedAt: null,
        ),
      ],
      createdAt: DateTime.utc(2026, 7, 28),
      updatedAt: DateTime.utc(2026, 7, 28),
    );
  }
}
