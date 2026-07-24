import 'package:boxbrain_ui/app.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows the offline mission-control dashboard', (tester) async {
    await tester.pumpWidget(const BoxBrainApp());

    expect(find.text('BoxBrain'), findsOneWidget);
    expect(find.text('Mission control'), findsOneWidget);
    expect(find.text('Offline'), findsWidgets);
    expect(find.text('Task queue'), findsOneWidget);
  });
}

