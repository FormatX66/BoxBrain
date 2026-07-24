import 'package:flutter/material.dart';

import '../models/controller_status.dart';
import '../widgets/section_card.dart';
import '../widgets/stat_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static const _destinations = [
    NavigationRailDestination(
      icon: Icon(Icons.space_dashboard_outlined),
      selectedIcon: Icon(Icons.space_dashboard),
      label: Text('Dashboard'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.task_alt_outlined),
      selectedIcon: Icon(Icons.task_alt),
      label: Text('Tasks'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.policy_outlined),
      selectedIcon: Icon(Icons.policy),
      label: Text('Policies'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.extension_outlined),
      selectedIcon: Icon(Icons.extension),
      label: Text('Plugins'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.receipt_long_outlined),
      selectedIcon: Icon(Icons.receipt_long),
      label: Text('Logs'),
    ),
  ];

  static const _status = ControllerStatus.offline();
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        final body = IndexedStack(
          index: _selectedIndex,
          children: const [
            _Overview(status: _status),
            _EmptySection(
              icon: Icons.task_alt,
              title: 'No tasks queued',
              message: 'Connect the controller before creating a task.',
            ),
            _EmptySection(
              icon: Icons.policy,
              title: 'Policy profiles',
              message: 'Safe is the default profile for new targets.',
            ),
            _EmptySection(
              icon: Icons.extension,
              title: 'No plugins enabled',
              message: 'Plugin discovery is exposed by the controller API.',
            ),
            _EmptySection(
              icon: Icons.receipt_long,
              title: 'No activity yet',
              message: 'Controller events and task decisions will appear here.',
            ),
          ],
        );

        return Scaffold(
          appBar: wide
              ? null
              : AppBar(
                  title: const Text('BoxBrain'),
                  actions: const [_ConnectionBadge(), SizedBox(width: 16)],
                ),
          body: Row(
            children: [
              if (wide)
                NavigationRail(
                  extended: constraints.maxWidth >= 1180,
                  minExtendedWidth: 210,
                  leading: const Padding(
                    padding: EdgeInsets.fromLTRB(12, 22, 12, 28),
                    child: _Brand(),
                  ),
                  trailing: const Expanded(
                    child: Align(
                      alignment: Alignment.bottomCenter,
                      child: Padding(
                        padding: EdgeInsets.only(bottom: 20),
                        child: _ConnectionBadge(),
                      ),
                    ),
                  ),
                  destinations: _destinations,
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _selectDestination,
                ),
              Expanded(child: body),
            ],
          ),
          bottomNavigationBar: wide
              ? null
              : NavigationBar(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _selectDestination,
                  destinations: _destinations
                      .map(
                        (destination) => NavigationDestination(
                          icon: destination.icon,
                          selectedIcon: destination.selectedIcon,
                          label: (destination.label as Text).data!,
                        ),
                      )
                      .toList(),
                ),
        );
      },
    );
  }

  void _selectDestination(int index) {
    setState(() => _selectedIndex = index);
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          Icons.hub,
          color: Theme.of(context).colorScheme.primary,
          size: 30,
        ),
        const SizedBox(width: 10),
        Text('BoxBrain', style: Theme.of(context).textTheme.titleLarge),
      ],
    );
  }
}

class _ConnectionBadge extends StatelessWidget {
  const _ConnectionBadge();

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Controller offline',
      child: Chip(
        avatar: const Icon(Icons.circle, color: Colors.orange, size: 10),
        label: const Text('Offline'),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
    );
  }
}

class _Overview extends StatelessWidget {
  const _Overview({required this.status});

  final ControllerStatus status;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(28),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1300),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Mission control',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 6),
              Text(
                'Observe, queue, and audit work on isolated targets.',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 24),
              GridView.count(
                crossAxisCount:
                    MediaQuery.sizeOf(context).width >= 1050 ? 4 : 2,
                crossAxisSpacing: 14,
                mainAxisSpacing: 14,
                childAspectRatio: 2.2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  const StatTile(
                    label: 'Controller',
                    value: 'Offline',
                    icon: Icons.power_settings_new,
                    accent: Colors.orange,
                  ),
                  StatTile(
                    label: 'Active tasks',
                    value: status.activeTasks.toString(),
                    icon: Icons.task_alt,
                  ),
                  StatTile(
                    label: 'Enabled plugins',
                    value: status.enabledPlugins.toString(),
                    icon: Icons.extension,
                  ),
                  StatTile(
                    label: 'Policy profile',
                    value: status.policyProfile,
                    icon: Icons.shield_outlined,
                    accent: Colors.greenAccent,
                  ),
                ],
              ),
              const SizedBox(height: 20),
              const _OverviewCards(),
            ],
          ),
        ),
      ),
    );
  }
}

class _OverviewCards extends StatelessWidget {
  const _OverviewCards();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cards = [
          SectionCard(
            title: 'Target',
            subtitle: 'No remote target configured',
            trailing: FilledButton.icon(
              onPressed: null,
              icon: const Icon(Icons.add_link),
              label: const Text('Add target'),
            ),
            child: const _PlaceholderRows(
              rows: [
                ('Connection', 'Not configured'),
                ('Transport', 'RDP or VNC plugin'),
                ('Last frame', '—'),
              ],
            ),
          ),
          const SectionCard(
            title: 'Task queue',
            subtitle: 'Tasks wait for an authenticated controller',
            child: _Callout(
              icon: Icons.inbox_outlined,
              title: 'Queue is empty',
              message: 'The alpha API accepts tasks but executes nothing yet.',
            ),
          ),
          const SectionCard(
            title: 'Recent activity',
            subtitle: 'Audit events are kept separate from model output',
            child: _Callout(
              icon: Icons.history,
              title: 'No events recorded',
              message: 'Start the controller to generate health events.',
            ),
          ),
          const SectionCard(
            title: 'Safety state',
            subtitle: 'Containment and logging remain mandatory',
            child: _PlaceholderRows(
              rows: [
                ('Profile', 'Safe'),
                ('Target allowlist', 'Required'),
                ('Emergency stop', 'Armed'),
              ],
            ),
          ),
        ];

        if (constraints.maxWidth < 820) {
          return Column(
            children: [
              for (final card in cards) ...[card, const SizedBox(height: 14)],
            ],
          );
        }

        return GridView.count(
          crossAxisCount: 2,
          crossAxisSpacing: 14,
          mainAxisSpacing: 14,
          childAspectRatio: 1.55,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: cards,
        );
      },
    );
  }
}

class _PlaceholderRows extends StatelessWidget {
  const _PlaceholderRows({required this.rows});

  final List<(String, String)> rows;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final row in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(
              children: [
                Expanded(child: Text(row.$1)),
                Text(
                  row.$2,
                  style: TextStyle(color: Theme.of(context).colorScheme.outline),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _Callout extends StatelessWidget {
  const _Callout({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(message),
            ],
          ),
        ),
      ],
    );
  }
}

class _EmptySection extends StatelessWidget {
  const _EmptySection({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 54, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 18),
              Text(title, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text(message, textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
    );
  }
}

