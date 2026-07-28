from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from .models import RemoteTargetRecord


MachineKind = Literal[
    "workstation",
    "server",
    "virtual-machine",
    "raspberry-pi",
    "cloud-service",
    "other",
]
MachineStatus = Literal["detected", "provisioning", "ready", "offline"]
ProvisioningStatus = Literal["in_progress", "completed"]
ProvisioningStepStatus = Literal["pending", "completed"]
ProvisioningStepMode = Literal["automatic", "operator", "external-guided"]


class FleetError(ValueError):
    """Base error for invalid fleet operations."""


class FleetMachineNotFoundError(FleetError):
    """Raised when a fleet machine cannot be found."""


class ProvisioningNotFoundError(FleetError):
    """Raised when a provisioning run cannot be found."""


class FleetMachineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: MachineKind
    remote_target_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    notes: str | None = Field(default=None, max_length=1_000)
    authorization: Literal["AUTHORIZED"]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must contain non-whitespace text")
        return normalized

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        normalized = {" ".join(value.split()).lower() for value in values}
        normalized.discard("")
        return sorted(normalized)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class FleetImportRequest(BaseModel):
    confirmation: Literal["IMPORT"]


class ProvisioningStartRequest(BaseModel):
    confirmation: Literal["PROVISION"]


class ProvisioningStepCompleteRequest(BaseModel):
    confirmation: Literal["COMPLETE"]
    note: str | None = Field(default=None, max_length=1_000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class FleetMachine(BaseModel):
    id: UUID
    machine_identity: str
    name: str
    kind: MachineKind
    status: MachineStatus
    remote_target_id: UUID | None
    capabilities: tuple[str, ...]
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProvisioningStep(BaseModel):
    id: str
    position: int = Field(ge=1)
    title: str
    instructions: str
    mode: ProvisioningStepMode
    status: ProvisioningStepStatus
    note: str | None = None
    completed_at: datetime | None = None


class ProvisioningRun(BaseModel):
    id: UUID
    machine_id: UUID
    status: ProvisioningStatus
    current_step_id: str | None
    steps: tuple[ProvisioningStep, ...]
    created_at: datetime
    updated_at: datetime


class FleetDashboard(BaseModel):
    architecture_version: Literal["1.0"] = "1.0"
    machine_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    provisioning_count: int = Field(ge=0)
    active_run_count: int = Field(ge=0)
    machines: tuple[FleetMachine, ...]


_KIND_PREFIX: dict[MachineKind, str] = {
    "workstation": "WS",
    "server": "SRV",
    "virtual-machine": "VM",
    "raspberry-pi": "RPI",
    "cloud-service": "CLD",
    "other": "NODE",
}

_PROVISIONING_STEPS: tuple[
    tuple[str, str, str, ProvisioningStepMode], ...
] = (
    (
        "detect-machine",
        "Detect machine",
        "Confirm the machine record and optional authorized target link.",
        "automatic",
    ),
    (
        "name-machine",
        "Name machine",
        "Confirm the unique operator-facing machine name.",
        "automatic",
    ),
    (
        "generate-identity",
        "Generate Machine ID",
        "Create the durable BoxBrain machine identity.",
        "automatic",
    ),
    (
        "open-google-signup",
        "Open Google account setup",
        "Open Google account creation in a user-controlled browser.",
        "external-guided",
    ),
    (
        "complete-captcha",
        "Complete CAPTCHA",
        "The operator completes any identity or CAPTCHA challenge directly.",
        "operator",
    ),
    (
        "confirm-gmail",
        "Confirm dedicated Gmail",
        "Confirm this machine has its own mailbox; do not enter its password here.",
        "operator",
    ),
    (
        "confirm-drive",
        "Confirm dedicated Google Drive",
        "Confirm the machine Drive exists; BoxBrain stores no account credential.",
        "operator",
    ),
    (
        "create-drive-folders",
        "Create Drive folder structure",
        "Create Logs, Config, Projects, Repositories, Backups, Media, and Diagnostics.",
        "external-guided",
    ),
    (
        "configure-github",
        "Configure GitHub identity",
        "Configure a dedicated GitHub identity through an operator-controlled flow.",
        "operator",
    ),
    (
        "clone-repositories",
        "Clone required repositories",
        "Review repository scope before cloning through Brain Connect.",
        "operator",
    ),
    (
        "install-software",
        "Install required software",
        "Review and approve the machine-specific installation plan.",
        "operator",
    ),
    (
        "register-brain-connect",
        "Register with Brain Connect",
        "Link the authorized remote target or edge-agent transport.",
        "automatic",
    ),
    (
        "register-fleet",
        "Register with Fleet Manager",
        "Persist inventory and lifecycle state.",
        "automatic",
    ),
    (
        "register-capabilities",
        "Register capabilities",
        "Persist the declared machine capability catalog.",
        "automatic",
    ),
    (
        "run-diagnostics",
        "Run diagnostics",
        "Use the existing approval-gated diagnostic surface for the linked target.",
        "operator",
    ),
    (
        "provisioning-report",
        "Complete provisioning report",
        "Review the final identity, capability, and onboarding summary.",
        "operator",
    ),
)


class FleetService:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = Lock()
        self._initialize()

    def list(self) -> list[FleetMachine]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, machine_identity, name, kind, status,
                       remote_target_id, capabilities_json, notes,
                       created_at, updated_at
                FROM fleet_machines
                ORDER BY name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._machine_from_row(row) for row in rows]

    def get(self, machine_id: UUID) -> FleetMachine:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, machine_identity, name, kind, status,
                       remote_target_id, capabilities_json, notes,
                       created_at, updated_at
                FROM fleet_machines WHERE id = ?
                """,
                (str(machine_id),),
            ).fetchone()
        if row is None:
            raise FleetMachineNotFoundError("Fleet machine not found.")
        return self._machine_from_row(row)

    def create(self, request: FleetMachineCreate) -> FleetMachine:
        machine_id = uuid4()
        now = datetime.now(UTC)
        identity = self._machine_identity(machine_id, request.kind)
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO fleet_machines (
                        id, machine_identity, name, kind, status,
                        remote_target_id, capabilities_json, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'detected', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(machine_id),
                        identity,
                        request.name,
                        request.kind,
                        (
                            str(request.remote_target_id)
                            if request.remote_target_id
                            else None
                        ),
                        json.dumps(request.capabilities, separators=(",", ":")),
                        request.notes,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise FleetError(
                "That machine name or remote target is already registered."
            ) from error
        return self.get(machine_id)

    def import_remote_targets(
        self,
        targets: list[RemoteTargetRecord],
    ) -> list[FleetMachine]:
        imported: list[FleetMachine] = []
        for target in targets:
            existing = self._get_by_remote_target(target.id)
            if existing is not None:
                imported.append(existing)
                continue
            kind: MachineKind = (
                "raspberry-pi"
                if target.transport == "usb-c"
                else "workstation"
                if target.transport in {"rdp", "winrm"}
                else "other"
            )
            imported.append(
                self.create(
                    FleetMachineCreate(
                        name=target.name,
                        kind=kind,
                        remote_target_id=target.id,
                        capabilities=list(target.capabilities),
                        notes="Imported from the authorized remote-target registry.",
                        authorization="AUTHORIZED",
                    )
                )
            )
        return imported

    def dashboard(self) -> FleetDashboard:
        machines = self.list()
        with self._lock, self._connect() as connection:
            active = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM provisioning_runs
                    WHERE status = 'in_progress'
                    """
                ).fetchone()["count"]
            )
        return FleetDashboard(
            machine_count=len(machines),
            ready_count=sum(item.status == "ready" for item in machines),
            provisioning_count=sum(
                item.status == "provisioning" for item in machines
            ),
            active_run_count=active,
            machines=tuple(machines),
        )

    def start_provisioning(self, machine_id: UUID) -> ProvisioningRun:
        machine = self.get(machine_id)
        existing = self.get_provisioning(machine_id)
        if existing is not None and existing.status == "in_progress":
            return existing
        run_id = uuid4()
        now = datetime.now(UTC)
        automatic_completed = {
            "detect-machine",
            "name-machine",
            "generate-identity",
            "register-fleet",
            "register-capabilities",
        }
        if machine.remote_target_id is not None:
            automatic_completed.add("register-brain-connect")
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO provisioning_runs (
                    id, machine_id, status, created_at, updated_at
                ) VALUES (?, ?, 'in_progress', ?, ?)
                """,
                (
                    str(run_id),
                    str(machine_id),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            for position, (step_id, title, instructions, mode) in enumerate(
                _PROVISIONING_STEPS,
                start=1,
            ):
                completed = step_id in automatic_completed
                connection.execute(
                    """
                    INSERT INTO provisioning_steps (
                        run_id, step_id, position, title, instructions, mode,
                        status, note, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(run_id),
                        step_id,
                        position,
                        title,
                        instructions,
                        mode,
                        "completed" if completed else "pending",
                        "Completed from local machine registration."
                        if completed
                        else None,
                        now.isoformat() if completed else None,
                    ),
                )
            connection.execute(
                """
                UPDATE fleet_machines
                SET status = 'provisioning', updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), str(machine_id)),
            )
        return self.get_run(run_id)

    def get_provisioning(self, machine_id: UUID) -> ProvisioningRun | None:
        self.get(machine_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM provisioning_runs
                WHERE machine_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (str(machine_id),),
            ).fetchone()
        return self.get_run(UUID(row["id"])) if row is not None else None

    def get_run(self, run_id: UUID) -> ProvisioningRun:
        with self._lock, self._connect() as connection:
            run_row = connection.execute(
                """
                SELECT id, machine_id, status, created_at, updated_at
                FROM provisioning_runs WHERE id = ?
                """,
                (str(run_id),),
            ).fetchone()
            step_rows = (
                connection.execute(
                    """
                    SELECT step_id, position, title, instructions, mode,
                           status, note, completed_at
                    FROM provisioning_steps
                    WHERE run_id = ? ORDER BY position ASC
                    """,
                    (str(run_id),),
                ).fetchall()
                if run_row is not None
                else []
            )
        if run_row is None:
            raise ProvisioningNotFoundError("Provisioning run not found.")
        steps = tuple(self._step_from_row(row) for row in step_rows)
        current = next((step.id for step in steps if step.status == "pending"), None)
        return ProvisioningRun(
            id=run_row["id"],
            machine_id=run_row["machine_id"],
            status=run_row["status"],
            current_step_id=current,
            steps=steps,
            created_at=datetime.fromisoformat(run_row["created_at"]),
            updated_at=datetime.fromisoformat(run_row["updated_at"]),
        )

    def complete_step(
        self,
        run_id: UUID,
        step_id: str,
        request: ProvisioningStepCompleteRequest,
    ) -> ProvisioningRun:
        run = self.get_run(run_id)
        if run.status == "completed":
            return run
        if run.current_step_id != step_id:
            raise FleetError("Complete the current provisioning step first.")
        now = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE provisioning_steps
                SET status = 'completed', note = ?, completed_at = ?
                WHERE run_id = ? AND step_id = ? AND status = 'pending'
                """,
                (request.note, now.isoformat(), str(run_id), step_id),
            )
            pending = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM provisioning_steps
                    WHERE run_id = ? AND status = 'pending'
                    """,
                    (str(run_id),),
                ).fetchone()["count"]
            )
            if pending == 0:
                connection.execute(
                    """
                    UPDATE provisioning_runs
                    SET status = 'completed', updated_at = ? WHERE id = ?
                    """,
                    (now.isoformat(), str(run_id)),
                )
                connection.execute(
                    """
                    UPDATE fleet_machines
                    SET status = 'ready', updated_at = ? WHERE id = ?
                    """,
                    (now.isoformat(), str(run.machine_id)),
                )
            else:
                connection.execute(
                    """
                    UPDATE provisioning_runs SET updated_at = ? WHERE id = ?
                    """,
                    (now.isoformat(), str(run_id)),
                )
        return self.get_run(run_id)

    def _get_by_remote_target(self, target_id: UUID) -> FleetMachine | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, machine_identity, name, kind, status,
                       remote_target_id, capabilities_json, notes,
                       created_at, updated_at
                FROM fleet_machines WHERE remote_target_id = ?
                """,
                (str(target_id),),
            ).fetchone()
        return self._machine_from_row(row) if row is not None else None

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS fleet_machines (
                    id TEXT PRIMARY KEY,
                    machine_identity TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    remote_target_id TEXT UNIQUE,
                    capabilities_json TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS provisioning_runs (
                    id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (machine_id) REFERENCES fleet_machines(id)
                );

                CREATE TABLE IF NOT EXISTS provisioning_steps (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    completed_at TEXT,
                    PRIMARY KEY (run_id, step_id),
                    FOREIGN KEY (run_id) REFERENCES provisioning_runs(id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _machine_identity(machine_id: UUID, kind: MachineKind) -> str:
        return f"BB-{_KIND_PREFIX[kind]}-{machine_id.hex[:12].upper()}"

    @staticmethod
    def _machine_from_row(row: sqlite3.Row) -> FleetMachine:
        return FleetMachine(
            id=row["id"],
            machine_identity=row["machine_identity"],
            name=row["name"],
            kind=row["kind"],
            status=row["status"],
            remote_target_id=row["remote_target_id"],
            capabilities=tuple(json.loads(row["capabilities_json"])),
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _step_from_row(row: sqlite3.Row) -> ProvisioningStep:
        return ProvisioningStep(
            id=row["step_id"],
            position=int(row["position"]),
            title=row["title"],
            instructions=row["instructions"],
            mode=row["mode"],
            status=row["status"],
            note=row["note"],
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
        )
