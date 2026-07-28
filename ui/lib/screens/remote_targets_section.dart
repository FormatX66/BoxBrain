import 'dart:async';

import 'package:flutter/material.dart';

import '../models/controller_status.dart';
import '../services/controller_api.dart';
import '../widgets/section_card.dart';

class RemoteTargetsPanel extends StatefulWidget {
  const RemoteTargetsPanel({
    required this.api,
    required this.targets,
    required this.emergencyStop,
    required this.onRefresh,
    super.key,
  });

  final ControllerApi api;
  final List<RemoteTargetSummary> targets;
  final EmergencyStopState emergencyStop;
  final VoidCallback onRefresh;

  @override
  State<RemoteTargetsPanel> createState() => _RemoteTargetsPanelState();
}

class _RemoteTargetsPanelState extends State<RemoteTargetsPanel> {
  Set<String> _busyTargets = const {};
  bool _adding = false;
  String? _lastMessage;

  Future<void> _addTarget() async {
    if (_adding) return;
    setState(() => _adding = true);
    try {
      final created = await showDialog<bool>(
        context: context,
        builder: (context) => _AddRemoteTargetDialog(api: widget.api),
      );
      if (!mounted || created != true) return;
      widget.onRefresh();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Authorized target added.')),
      );
    } finally {
      if (mounted) setState(() => _adding = false);
    }
  }

  Future<void> _probe(RemoteTargetSummary target) async {
    if (_busyTargets.contains(target.id)) return;
    _setBusy(target.id, true);
    try {
      final result = await widget.api.probeRemoteTarget(target.id);
      if (!mounted) return;
      widget.onRefresh();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message)),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    } finally {
      if (mounted) _setBusy(target.id, false);
    }
  }

  Future<void> _openSession(RemoteTargetSummary target) async {
    if (_busyTargets.contains(target.id) || widget.emergencyStop.engaged)
      return;
    final insecureConfirmation = await showDialog<String>(
      context: context,
      builder: (context) => _OpenRemoteSessionDialog(target: target),
    );
    if (!mounted || insecureConfirmation == null) return;
    _setBusy(target.id, true);
    try {
      final result = await widget.api.openRemoteTargetSession(
        targetId: target.id,
        insecureConfirmation:
            insecureConfirmation.isEmpty ? null : insecureConfirmation,
      );
      if (!mounted) return;
      setState(() => _lastMessage = result.message);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message)),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _lastMessage = error.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    } finally {
      if (mounted) _setBusy(target.id, false);
    }
  }

  Future<void> _remove(RemoteTargetSummary target) async {
    if (target.builtIn || _busyTargets.contains(target.id)) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove target?'),
        content: Text(
          'Remove ${target.name} from BoxBrain? This does not change the host.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) return;
    _setBusy(target.id, true);
    try {
      await widget.api.deleteRemoteTarget(target.id);
      if (!mounted) return;
      widget.onRefresh();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Target removed.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    } finally {
      if (mounted) _setBusy(target.id, false);
    }
  }

  void _setBusy(String targetId, bool busy) {
    setState(() {
      _busyTargets = {..._busyTargets};
      if (busy) {
        _busyTargets.add(targetId);
      } else {
        _busyTargets.remove(targetId);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      title: 'Connected hosts',
      subtitle: 'Authorized private targets and operator-controlled sessions',
      trailing: FilledButton.icon(
        key: const Key('add-remote-target'),
        onPressed: _adding ? null : _addTarget,
        icon: _adding
            ? const SizedBox.square(
                dimension: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.add_link),
        label: Text(_adding ? 'Adding' : 'Add target'),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: const ListTile(
              leading: Icon(Icons.security),
              title: Text('Operator-controlled access'),
              subtitle: Text(
                'BoxBrain stores no passwords and accepts only private, '
                'loopback, or link-local targets. Opening a session requires '
                'confirmation and a clear emergency stop.',
              ),
            ),
          ),
          if (_lastMessage != null) ...[
            const SizedBox(height: 10),
            Card(
              child: ListTile(
                key: const Key('remote-operation-result'),
                leading: const Icon(Icons.check_circle_outline),
                title: const Text('Last target action'),
                subtitle: Text(_lastMessage!),
              ),
            ),
          ],
          if (widget.emergencyStop.engaged) ...[
            const SizedBox(height: 10),
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: const ListTile(
                leading: Icon(Icons.stop_circle),
                title: Text('Remote sessions are blocked'),
                subtitle: Text('Reset the emergency stop before connecting.'),
              ),
            ),
          ],
          const SizedBox(height: 12),
          if (widget.targets.isEmpty)
            const Text('No authorized remote targets are registered.')
          else
            for (final target in widget.targets) ...[
              _RemoteTargetCard(
                target: target,
                busy: _busyTargets.contains(target.id),
                sessionBlocked: widget.emergencyStop.engaged,
                onProbe: () => unawaited(_probe(target)),
                onOpen: () => unawaited(_openSession(target)),
                onRemove:
                    target.builtIn ? null : () => unawaited(_remove(target)),
              ),
              const SizedBox(height: 10),
            ],
        ],
      ),
    );
  }
}

class _RemoteTargetCard extends StatelessWidget {
  const _RemoteTargetCard({
    required this.target,
    required this.busy,
    required this.sessionBlocked,
    required this.onProbe,
    required this.onOpen,
    required this.onRemove,
  });

  final RemoteTargetSummary target;
  final bool busy;
  final bool sessionBlocked;
  final VoidCallback onProbe;
  final VoidCallback onOpen;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final online = target.status == 'online';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(child: Icon(_transportIcon(target.transport))),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        target.name,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text('${target.host}:${target.port}'),
                    ],
                  ),
                ),
                Chip(
                  avatar: Icon(
                    online ? Icons.check_circle : Icons.circle_outlined,
                    size: 16,
                  ),
                  label: Text(_titleCase(target.status)),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Chip(label: Text(target.transport.toUpperCase())),
                Chip(label: Text(_credentialLabel(target.credentialMode))),
                if (target.builtIn) const Chip(label: Text('Built-in USB-C')),
                for (final capability in target.capabilities)
                  Chip(label: Text(capability.replaceAll('-', ' '))),
              ],
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    key: Key('probe-remote-${target.id}'),
                    onPressed: busy ? null : onProbe,
                    icon: const Icon(Icons.network_ping),
                    label: const Text('Test'),
                  ),
                  FilledButton.icon(
                    key: Key('open-remote-${target.id}'),
                    onPressed: busy || sessionBlocked ? null : onOpen,
                    icon: const Icon(Icons.open_in_new),
                    label: const Text('Open session'),
                  ),
                  if (onRemove != null)
                    IconButton.outlined(
                      key: Key('remove-remote-${target.id}'),
                      tooltip: 'Remove target',
                      onPressed: busy ? null : onRemove,
                      icon: const Icon(Icons.delete_outline),
                    ),
                ],
              ),
            ),
            if (busy) ...[
              const SizedBox(height: 10),
              const LinearProgressIndicator(),
            ],
          ],
        ),
      ),
    );
  }
}

class _AddRemoteTargetDialog extends StatefulWidget {
  const _AddRemoteTargetDialog({required this.api});

  final ControllerApi api;

  @override
  State<_AddRemoteTargetDialog> createState() => _AddRemoteTargetDialogState();
}

class _AddRemoteTargetDialogState extends State<_AddRemoteTargetDialog> {
  static const _ports = {
    'usb-c': 22,
    'ssh': 22,
    'winrm': 5986,
    'rdp': 3389,
    'telnet': 23,
  };

  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _host = TextEditingController();
  final _port = TextEditingController(text: '22');
  final _username = TextEditingController();
  String _transport = 'ssh';
  bool _authorized = false;
  bool _telnetAcknowledged = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _host.dispose();
    _port.dispose();
    _username.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add authorized target'),
      content: SizedBox(
        width: 560,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  key: const Key('remote-transport'),
                  initialValue: _transport,
                  decoration: const InputDecoration(
                    labelText: 'Connection type',
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 'usb-c', child: Text('USB-C SSH')),
                    DropdownMenuItem(value: 'ssh', child: Text('SSH')),
                    DropdownMenuItem(
                        value: 'winrm',
                        child: Text('Windows Remote Management')),
                    DropdownMenuItem(
                        value: 'rdp', child: Text('Windows Remote Desktop')),
                    DropdownMenuItem(
                        value: 'telnet',
                        child: Text('Telnet (legacy/plaintext)')),
                  ],
                  onChanged: _submitting
                      ? null
                      : (value) {
                          if (value == null) return;
                          setState(() {
                            _transport = value;
                            _port.text = _ports[value].toString();
                          });
                        },
                ),
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('remote-name'),
                  controller: _name,
                  enabled: !_submitting,
                  decoration: const InputDecoration(
                    labelText: 'Display name',
                    border: OutlineInputBorder(),
                  ),
                  validator: _required,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('remote-host'),
                  controller: _host,
                  enabled: !_submitting,
                  decoration: const InputDecoration(
                    labelText: 'Private IP or hostname',
                    hintText: '192.168.1.50 or repair-pc.local',
                    border: OutlineInputBorder(),
                  ),
                  validator: _required,
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        key: const Key('remote-username'),
                        controller: _username,
                        enabled: !_submitting,
                        decoration: const InputDecoration(
                          labelText: 'Username (optional)',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 120,
                      child: TextFormField(
                        key: const Key('remote-port'),
                        controller: _port,
                        enabled: !_submitting,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Port',
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) {
                          final port = int.tryParse(value ?? '');
                          return port == null || port < 1 || port > 65535
                              ? 'Invalid port'
                              : null;
                        },
                      ),
                    ),
                  ],
                ),
                if (_transport == 'telnet')
                  CheckboxListTile(
                    value: _telnetAcknowledged,
                    onChanged: _submitting
                        ? null
                        : (value) => setState(
                              () => _telnetAcknowledged = value ?? false,
                            ),
                    title: const Text('I understand Telnet is plaintext'),
                    subtitle: const Text(
                      'Use only on an isolated legacy lab network.',
                    ),
                    contentPadding: EdgeInsets.zero,
                  ),
                CheckboxListTile(
                  key: const Key('remote-authorized'),
                  value: _authorized,
                  onChanged: _submitting
                      ? null
                      : (value) => setState(() => _authorized = value ?? false),
                  title: const Text('I am authorized to access this host'),
                  subtitle: const Text(
                    'Passwords are never saved by BoxBrain.',
                  ),
                  contentPadding: EdgeInsets.zero,
                ),
                if (_error != null)
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          key: const Key('confirm-add-remote'),
          onPressed: _submitting ? null : _submit,
          icon: _submitting
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.add_link),
          label: Text(_submitting ? 'Adding' : 'Add target'),
        ),
      ],
    );
  }

  String? _required(String? value) =>
      value == null || value.trim().isEmpty ? 'This field is required.' : null;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (!_authorized) {
      setState(() => _error = 'Confirm that this host is authorized.');
      return;
    }
    if (_transport == 'telnet' && !_telnetAcknowledged) {
      setState(() => _error = 'Acknowledge the Telnet plaintext warning.');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createRemoteTarget(
        name: _name.text.trim(),
        transport: _transport,
        host: _host.text.trim(),
        port: int.parse(_port.text),
        username: _username.text,
        insecureTransportAcknowledged: _telnetAcknowledged,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = error.toString();
      });
    }
  }
}

class _OpenRemoteSessionDialog extends StatefulWidget {
  const _OpenRemoteSessionDialog({required this.target});

  final RemoteTargetSummary target;

  @override
  State<_OpenRemoteSessionDialog> createState() =>
      _OpenRemoteSessionDialogState();
}

class _OpenRemoteSessionDialogState extends State<_OpenRemoteSessionDialog> {
  final _confirmation = TextEditingController();
  final _telnetConfirmation = TextEditingController();

  @override
  void dispose() {
    _confirmation.dispose();
    _telnetConfirmation.dispose();
    super.dispose();
  }

  bool get _ready =>
      _confirmation.text.trim() == 'OPEN' &&
      (widget.target.transport != 'telnet' ||
          _telnetConfirmation.text.trim() ==
              'I UNDERSTAND TELNET IS PLAINTEXT');

  @override
  Widget build(BuildContext context) {
    final telnet = widget.target.transport == 'telnet';
    return AlertDialog(
      title: Text('Open ${widget.target.name}?'),
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'BoxBrain will launch the operating-system client for '
              '${widget.target.transport.toUpperCase()}. You remain in '
              'control of authentication and every command.',
            ),
            const SizedBox(height: 14),
            TextField(
              key: const Key('remote-open-confirmation'),
              controller: _confirmation,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                labelText: 'Type OPEN',
                border: OutlineInputBorder(),
              ),
            ),
            if (telnet) ...[
              const SizedBox(height: 12),
              TextField(
                key: const Key('telnet-open-confirmation'),
                controller: _telnetConfirmation,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Type I UNDERSTAND TELNET IS PLAINTEXT',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          key: const Key('confirm-open-remote'),
          onPressed: _ready
              ? () => Navigator.pop(
                    context,
                    telnet ? _telnetConfirmation.text.trim() : '',
                  )
              : null,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open session'),
        ),
      ],
    );
  }
}

IconData _transportIcon(String transport) => switch (transport) {
      'usb-c' => Icons.usb,
      'ssh' => Icons.terminal,
      'winrm' => Icons.terminal_outlined,
      'rdp' => Icons.desktop_windows,
      'telnet' => Icons.settings_ethernet,
      _ => Icons.device_hub,
    };

String _credentialLabel(String mode) => switch (mode) {
      'dedicated-key' => 'Dedicated key',
      'ssh-agent' => 'SSH agent / prompt',
      'current-user' => 'Current Windows user',
      'interactive' => 'Interactive sign-in',
      _ => 'No stored credential',
    };

String _titleCase(String value) =>
    value.isEmpty ? value : '${value[0].toUpperCase()}${value.substring(1)}';
