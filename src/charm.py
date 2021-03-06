#!/usr/bin/env python3
"""FluentbitCharm."""

import logging
import json
from pathlib import Path

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from fluentbit_ops import FluentbitOps
from charms.fluentbit.v0.fluentbit import FluentbitProvider

logger = logging.getLogger(__name__)
VERSION = Path("version").read_text().strip()


class FluentbitCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        """Initialize charm."""

        super().__init__(*args)

        self._fluentbit = FluentbitOps()
        self._fluentbit_provider = FluentbitProvider(self, "fluentbit")

        self._stored.set_default(installed=False)

        # juju core hooks
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.update_status, self._on_update_status)

        # handle fluentbit relation event and configure and restart it
        self.framework.observe(self._fluentbit_provider.on.configuration_available,
                               self._on_config_changed)

    def _on_install(self, event):
        logger.debug("## Installing charm")
        self.unit.status = MaintenanceStatus("Installing Fluentbit")
        # subordinate charms do not have a leader.
        self.unit.set_workload_version(VERSION)

        if self._fluentbit.install():
            self.unit.status = ActiveStatus("Fluentbit installed")
            self._stored.installed = True
        else:
            self.unit.status = BlockedStatus("Error installing Fluentbit")
            event.defer()

    def _on_upgrade_charm(self, event):
        """Perform charm upgrade operations."""
        logger.debug("## Upgrading charm")
        self.unit.status = MaintenanceStatus("Upgrading Fluentbit")
        self.unit.set_workload_version(VERSION)

        self.unit.status = ActiveStatus("Fluentbit upgraded")

    def _on_config_changed(self, event):
        """Handle configuration updates."""
        logger.debug("## Configuring charm")

        cfg = self._fluentbit_provider.configuration
        charm_config = self.model.config.get("custom-config", "[]")

        try:
            charm_configs = json.loads(charm_config or '[]')
        except json.JSONDecodeError as e:
            logger.error(f"Invalid Json for custom-config: {e}")
            charm_configs = []

        logger.debug(f"## config-changed: relation configs: {cfg}.")
        logger.debug(f"## config-changed: charm configs: {charm_configs}.")

        self._fluentbit.configure(cfg + charm_configs)
        self._check_status()

    def _on_start(self, event):
        logger.debug("## Starting daemon")
        if not self._fluentbit.restart():
            event.defer()
        self._check_status()

    def _on_stop(self, event):
        logger.debug("## Stopping daemon")
        self._fluentbit.stop()

    def _on_remove(self, event):
        logger.debug("## Uninstalling Fluentbit")
        self._fluentbit.uninstall()

    def _on_update_status(self, event):
        logger.debug("## Updating status")
        self._check_status()

    def _check_status(self):
        """Check status of the system.

        Returns:
            bool: True if the system is ready.
        """
        if not self._stored.installed:
            self.unit.status = MaintenanceStatus("Fluentbit not installed")
            return False

        if not self._fluentbit.is_active():
            self.unit.status = MaintenanceStatus("Fluentbit installed but not running")
            return False

        self.unit.status = ActiveStatus("Fluentbit started")
        return True


if __name__ == "__main__":
    main(FluentbitCharm)
