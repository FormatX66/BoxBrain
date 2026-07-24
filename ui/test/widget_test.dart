import 'package:boxbrain_ui/app.dart';
import 'package:boxbrain_ui/models/controller_status.dart';
import 'package:boxbrain_ui/services/controller_api.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows live controller data and resource views', (tester) async {
    await tester.pumpWidget(
      const BoxBrainApp(controllerApi: _OnlineControllerApi()),
    );
    await tester.pumpAndSettle();

    expect(find.text('BoxBrain'), findsOneWidget);
    expect(find.text('Mission control'), findsOneWidget);
    expect(find.text('Online'), findsWidgets);
    expect(find.text('0.1.0'), findsOneWidget);
    expect(find.text('1'), findsWidgets);

    await tester.tap(find.text('Policies'));
    await tester.pumpAndSettle();

    expect(find.text('3 profiles from the controller'), findsOneWidget);
    expect(find.text('Research'), findsOneWidget);
    expect(find.text('Open'), findsOneWidget);
  });

  testWidgets('shows retryable offline state when controller fails', (
    tester,
  ) async {
    await tester.pumpWidget(
      const BoxBrainApp(controllerApi: _OfflineControllerApi()),
    );
    await tester.pumpAndSettle();

    expect(find.text('Offline'), findsWidgets);
    expect(find.text('Controller is not reachable.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });
}

class _OnlineControllerApi extends ControllerApi {
  const _OnlineControllerApi();

  @override
  Future<ControllerHealth> fetchHealth() async => const ControllerHealth(
        service: 'boxbrain-controller',
        version: '0.1.0',
        status: 'ok',
        environment: 'development',
        executorEnabled: false,
      );

  @override
  Future<List<TaskSummary>> fetchTasks() async => const [];

  @override
  Future<List<PolicySummary>> fetchPolicies() async => const [
        PolicySummary(
          name: 'safe',
          description: 'Confirm consequential actions.',
          confirmationsRequired: true,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
        PolicySummary(
          name: 'research',
          description: 'Reduced confirmations in an isolated target.',
          confirmationsRequired: false,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
        PolicySummary(
          name: 'open',
          description: 'Experimental disposable-lab profile.',
          confirmationsRequired: false,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
      ];

  @override
  Future<List<PluginSummary>> fetchPlugins() async => const [
        PluginSummary(
          id: 'example-observer',
          name: 'Example observer',
          version: '0.1.0',
          description: 'Inert example plugin.',
          enabled: true,
        ),
      ];
}

class _OfflineControllerApi extends ControllerApi {
  const _OfflineControllerApi();

  @override
  Future<ControllerHealth> fetchHealth() async {
    throw const ControllerApiException('Controller is not reachable.');
  }

  @override
  Future<List<TaskSummary>> fetchTasks() async => const [];

  @override
  Future<List<PolicySummary>> fetchPolicies() async => const [];

  @override
  Future<List<PluginSummary>> fetchPlugins() async => const [];
}
