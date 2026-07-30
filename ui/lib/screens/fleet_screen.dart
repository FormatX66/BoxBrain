import 'package:flutter/material.dart';

import '../models/controller_status.dart';
import '../models/fleet_models.dart';
import '../services/controller_api.dart';

class FleetScreen extends StatefulWidget {
  const FleetScreen({
    required this.api,
    required this.active,
    super.key,
  });

  final ControllerApi api;
  final bool active;

  @override
  State<FleetScreen> createState() => _FleetScreenState();
}

class _FleetScreenState extends State<FleetScreen> {
  ArchitectureManifestSummary? _architecture;
  FleetDashboardSummary? _fleet;
  List<RemoteTargetSummary> _targets = const [];
  FleetMachineSummary? _selectedMachine;
  ProvisioningRunSummary? _run;
  bool _loaded = false;
  bool _loading = false;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.active) _load();
  }

  @override
  void didUpdateWidget(covariant FleetScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && !oldWidget.active && !_loaded) _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait<Object>([
        widget.api.fetchArchitecture(),
        widget.api.fetchFleet(),
        widget.api.fetchRemoteTargets(),
      ]);
      final fleet = results[1] as FleetDashboardSummary;
      FleetMachineSummary? selected;
      if (_selectedMachine != null) {
        selected = fleet.machines
            .where((item) => item.id == _selectedMachine!.id)
            .firstOrNull;
      }
      selected ??= fleet.machines.firstOrNull;
      ProvisioningRunSummary? run;
      if (selected != null) {
        run = await widget.api.fetchMachineProvisioning(selected.id);
      }
      if (!mounted) return;
      setState(() {
        _architecture = results[0] as ArchitectureManifestSummary;
        _fleet = fleet;
        _targets = results[2] as List<RemoteTargetSummary>;
        _selectedMachine = selected;
        _run = run;
        _loaded = true;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _importTargets() async {
    await _perform(
      () async {
        final machines = await widget.api.importFleetTargets();
        _notify('Synchronized ${machines.length} authorized target(s).');
        await _load();
      },
    );
  }

  Future<void> _registerMachine() async {
    final draft = await showDialog<_MachineDraft>(
      context: context,
      builder: (context) => _RegisterMachineDialog(targets: _targets),
    );
    if (draft == null) return;
    await _perform(
      () async {
        final machine = await widget.api.registerFleetMachine(
          name: draft.name,
          kind: draft.kind,
          remoteTargetId:
              draft.remoteTargetId.isEmpty ? null : draft.remoteTargetId,
          capabilities: draft.capabilities,
          notes: draft.notes,
        );
        _selectedMachine = machine;
        _notify('Registered ${machine.name}.');
        await _load();
      },
    );
  }

  Future<void> _selectMachine(FleetMachineSummary machine) async {
    setState(() {
      _selectedMachine = machine;
      _run = null;
      _busy = true;
    });
    try {
      final run = await widget.api.fetchMachineProvisioning(machine.id);
      if (!mounted) return;
      setState(() => _run = run);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _startProvisioning() async {
    final machine = _selectedMachine;
    if (machine == null) return;
    await _perform(
      () async {
        final run = await widget.api.startMachineProvisioning(machine.id);
        if (!mounted) return;
        setState(() => _run = run);
        _notify('Provisioning checklist ready.');
        await _load();
      },
    );
  }

  Future<void> _completeCurrentStep() async {
    final run = _run;
    final stepId = run?.currentStepId;
    if (run == null || stepId == null) return;
    final step = run.steps.firstWhere((item) => item.id == stepId);
    final note = await showDialog<String>(
      context: context,
      builder: (context) => _CompleteStepDialog(step: step),
    );
    if (note == null) return;
    await _perform(
      () async {
        final updated = await widget.api.completeProvisioningStep(
          runId: run.id,
          stepId: step.id,
          note: note,
        );
        if (!mounted) return;
        setState(() => _run = updated);
        _notify(
          updated.status == 'completed'
              ? 'Machine provisioning complete.'
              : 'Step completed. Next step is ready.',
        );
        await _load();
      },
    );
  }

  Future<void> _perform(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _notify(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final architecture = _architecture;
    final fleet = _fleet;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        key: const PageStorageKey('fleet-screen'),
        padding: const EdgeInsets.all(24),
        children: [
          _FleetHeader(
            version: architecture?.version,
            busy: _busy,
            onImport: _importTargets,
            onRegister: _registerMachine,
            onRefresh: _load,
          ),
          if (_loading && !_loaded) ...[
            const SizedBox(height: 32),
            const Center(child: CircularProgressIndicator()),
          ],
          if (_error != null) ...[
            const SizedBox(height: 16),
            _ErrorCard(message: _error!, onRetry: _load),
          ],
          if (fleet != null) ...[
            const SizedBox(height: 20),
            _FleetStats(fleet: fleet),
            const SizedBox(height: 20),
            _MachineInventory(
              fleet: fleet,
              selectedId: _selectedMachine?.id,
              busy: _busy,
              onSelected: _selectMachine,
            ),
            const SizedBox(height: 20),
            _ProvisioningCard(
              machine: _selectedMachine,
              run: _run,
              busy: _busy,
              onStart: _startProvisioning,
              onComplete: _completeCurrentStep,
            ),
          ],
          if (architecture != null) ...[
            const SizedBox(height: 20),
            _ArchitectureCard(architecture: architecture),
          ],
          const SizedBox(height: 40),
        ],
      ),
    );
  }
}

class _FleetHeader extends StatelessWidget {
  const _FleetHeader({
    required this.version,
    required this.busy,
    required this.onImport,
    required this.onRegister,
    required this.onRefresh,
  });

  final String? version;
  final bool busy;
  final VoidCallback onImport;
  final VoidCallback onRegister;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 16,
      runSpacing: 12,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Fleet & provisioning',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'One machine, one durable identity, one diagnostic history.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Chip(label: Text('Architecture v${version ?? '—'}')),
            OutlinedButton.icon(
              onPressed: busy ? null : onImport,
              icon: const Icon(Icons.sync),
              label: const Text('Import targets'),
            ),
            FilledButton.icon(
              onPressed: busy ? null : onRegister,
              icon: const Icon(Icons.add),
              label: const Text('Register machine'),
            ),
            IconButton(
              onPressed: busy ? null : onRefresh,
              tooltip: 'Refresh fleet',
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
      ],
    );
  }
}

class _FleetStats extends StatelessWidget {
  const _FleetStats({required this.fleet});

  final FleetDashboardSummary fleet;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        _Stat(label: 'Machines', value: '${fleet.machineCount}'),
        _Stat(label: 'Ready', value: '${fleet.readyCount}'),
        _Stat(label: 'Provisioning', value: '${fleet.provisioningCount}'),
        _Stat(label: 'Active runs', value: '${fleet.activeRunCount}'),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 150,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: Theme.of(context).textTheme.headlineSmall),
          Text(label),
        ],
      ),
    );
  }
}

class _MachineInventory extends StatelessWidget {
  const _MachineInventory({
    required this.fleet,
    required this.selectedId,
    required this.busy,
    required this.onSelected,
  });

  final FleetDashboardSummary fleet;
  final String? selectedId;
  final bool busy;
  final ValueChanged<FleetMachineSummary> onSelected;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Machine inventory',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text(
                'Authorized targets can be linked without copying credentials.'),
            const SizedBox(height: 12),
            if (fleet.machines.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 20),
                child:
                    Text('No machines registered. Import targets or add one.'),
              )
            else
              for (final machine in fleet.machines)
                ListTile(
                  key: Key('fleet-machine-${machine.id}'),
                  selected: selectedId == machine.id,
                  enabled: !busy,
                  onTap: () => onSelected(machine),
                  leading: Icon(_machineIcon(machine.kind)),
                  title: Text(machine.name),
                  subtitle: Text(
                    '${machine.machineIdentity} · ${machine.kind.replaceAll('-', ' ')}'
                    '${machine.remoteTargetId == null ? '' : ' · target linked'}',
                  ),
                  trailing: Chip(label: Text(_title(machine.status))),
                ),
          ],
        ),
      ),
    );
  }
}

class _ProvisioningCard extends StatelessWidget {
  const _ProvisioningCard({
    required this.machine,
    required this.run,
    required this.busy,
    required this.onStart,
    required this.onComplete,
  });

  final FleetMachineSummary? machine;
  final ProvisioningRunSummary? run;
  final bool busy;
  final VoidCallback onStart;
  final VoidCallback onComplete;

  @override
  Widget build(BuildContext context) {
    final currentId = run?.currentStepId;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Machine provisioning',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 4),
            Text(
              machine == null
                  ? 'Select a machine to begin.'
                  : '${machine!.name} · ${machine!.machineIdentity}',
            ),
            const SizedBox(height: 12),
            if (machine != null && run == null)
              FilledButton.icon(
                key: const Key('start-provisioning'),
                onPressed: busy ? null : onStart,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Start provisioning'),
              ),
            if (run != null) ...[
              Row(
                children: [
                  Chip(label: Text(_title(run!.status))),
                  const SizedBox(width: 8),
                  Text(
                    '${run!.steps.where((step) => step.status == 'completed').length}'
                    ' of ${run!.steps.length} complete',
                  ),
                ],
              ),
              const SizedBox(height: 12),
              for (final step in run!.steps)
                ListTile(
                  dense: true,
                  selected: step.id == currentId,
                  leading: CircleAvatar(
                    radius: 15,
                    child: step.status == 'completed'
                        ? const Icon(Icons.check, size: 18)
                        : Text('${step.position}'),
                  ),
                  title: Text(step.title),
                  subtitle: Text(
                    '${step.instructions}\n${_title(step.mode)}',
                  ),
                  isThreeLine: true,
                ),
              if (currentId != null)
                FilledButton.icon(
                  key: const Key('complete-provisioning-step'),
                  onPressed: busy ? null : onComplete,
                  icon: const Icon(Icons.task_alt),
                  label: const Text('Mark current step complete'),
                )
              else
                const ListTile(
                  leading: Icon(Icons.verified, color: Colors.green),
                  title: Text('Provisioning complete'),
                  subtitle: Text('The machine is ready in Fleet Manager.'),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ArchitectureCard extends StatelessWidget {
  const _ArchitectureCard({required this.architecture});

  final ArchitectureManifestSummary architecture;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${architecture.name} · v${architecture.version}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                for (var index = 0;
                    index < architecture.flow.length;
                    index++) ...[
                  Chip(label: Text(architecture.flow[index])),
                  if (index < architecture.flow.length - 1)
                    const Icon(Icons.arrow_forward, size: 18),
                ],
              ],
            ),
            const SizedBox(height: 16),
            Text(
              'System agent roster (${architecture.agents.length})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            for (final agent in architecture.agents)
              ExpansionTile(
                title: Text(agent.name),
                subtitle: Text(agent.mission),
                trailing: Chip(label: Text(_title(agent.maturity))),
                childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '${_title(agent.boundary)} · '
                      '${agent.responsibilities.join(', ')}',
                    ),
                  ),
                ],
              ),
            const SizedBox(height: 12),
            for (final note in architecture.compatibilityNotes)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.shield_outlined, size: 18),
                    const SizedBox(width: 8),
                    Expanded(child: Text(note)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _RegisterMachineDialog extends StatefulWidget {
  const _RegisterMachineDialog({required this.targets});

  final List<RemoteTargetSummary> targets;

  @override
  State<_RegisterMachineDialog> createState() => _RegisterMachineDialogState();
}

class _RegisterMachineDialogState extends State<_RegisterMachineDialog> {
  final _name = TextEditingController();
  final _capabilities = TextEditingController();
  final _notes = TextEditingController();
  String _kind = 'workstation';
  String _target = '';

  @override
  void dispose() {
    _name.dispose();
    _capabilities.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Register machine'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                key: const Key('fleet-machine-name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Machine name'),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Machine type'),
                items: const [
                  DropdownMenuItem(
                      value: 'workstation', child: Text('Workstation')),
                  DropdownMenuItem(value: 'server', child: Text('Server')),
                  DropdownMenuItem(
                    value: 'virtual-machine',
                    child: Text('Virtual machine'),
                  ),
                  DropdownMenuItem(
                    value: 'raspberry-pi',
                    child: Text('Raspberry Pi'),
                  ),
                  DropdownMenuItem(
                    value: 'cloud-service',
                    child: Text('Cloud service'),
                  ),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) => setState(() => _kind = value ?? _kind),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _target,
                decoration: const InputDecoration(
                  labelText: 'Authorized target (optional)',
                ),
                items: [
                  const DropdownMenuItem(
                      value: '', child: Text('No target link')),
                  for (final target in widget.targets)
                    DropdownMenuItem(
                        value: target.id, child: Text(target.name)),
                ],
                onChanged: (value) => setState(() => _target = value ?? ''),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _capabilities,
                decoration: const InputDecoration(
                  labelText: 'Capabilities (comma separated)',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _notes,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Notes'),
              ),
              const SizedBox(height: 12),
              const Text(
                'BoxBrain stores identity and capability metadata only. '
                'Do not enter passwords or API keys.',
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _name.text.trim().isEmpty
              ? null
              : () => Navigator.pop(
                    context,
                    _MachineDraft(
                      name: _name.text.trim(),
                      kind: _kind,
                      remoteTargetId: _target,
                      capabilities: _capabilities.text
                          .split(',')
                          .map((item) => item.trim())
                          .where((item) => item.isNotEmpty)
                          .toList(),
                      notes: _notes.text.trim(),
                    ),
                  ),
          child: const Text('Register'),
        ),
      ],
    );
  }
}

class _CompleteStepDialog extends StatefulWidget {
  const _CompleteStepDialog({required this.step});

  final ProvisioningStepSummary step;

  @override
  State<_CompleteStepDialog> createState() => _CompleteStepDialogState();
}

class _CompleteStepDialogState extends State<_CompleteStepDialog> {
  final _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Complete ${widget.step.title}?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.step.instructions),
          const SizedBox(height: 12),
          const Text(
            'Confirm only after the operator-controlled step is finished. '
            'Never paste passwords, recovery codes, or API keys.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _note,
            maxLines: 2,
            decoration:
                const InputDecoration(labelText: 'Completion note (optional)'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, _note.text.trim()),
          child: const Text('Mark complete'),
        ),
      ],
    );
  }
}

class _MachineDraft {
  const _MachineDraft({
    required this.name,
    required this.kind,
    required this.remoteTargetId,
    required this.capabilities,
    required this.notes,
  });

  final String name;
  final String kind;
  final String remoteTargetId;
  final List<String> capabilities;
  final String notes;
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: ListTile(
        leading: const Icon(Icons.error_outline),
        title: Text(message),
        trailing: TextButton(onPressed: onRetry, child: const Text('Retry')),
      ),
    );
  }
}

IconData _machineIcon(String kind) {
  return switch (kind) {
    'raspberry-pi' => Icons.memory,
    'virtual-machine' => Icons.view_in_ar,
    'cloud-service' => Icons.cloud_outlined,
    'server' => Icons.dns_outlined,
    _ => Icons.computer,
  };
}

String _title(String value) {
  if (value.isEmpty) return value;
  final normalized = value.replaceAll('-', ' ').replaceAll('_', ' ');
  return '${normalized[0].toUpperCase()}${normalized.substring(1)}';
}
