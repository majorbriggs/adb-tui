from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    Static,
)

from . import adb
from .adb import Action

# ---------------------------------------------------------------------------
# Typed ListItem subclasses — carry domain data alongside the visible label
# ---------------------------------------------------------------------------


class DeviceItem(ListItem):
    def __init__(self, device_id: str) -> None:
        super().__init__(Label(adb.format_device(device_id)))
        self.device_id = device_id


class ActionItem(ListItem):
    def __init__(self, action: Action) -> None:
        super().__init__(Label(action.value))
        self.action = action


class PackageItem(ListItem):
    def __init__(self, package: str) -> None:
        super().__init__(Label(package))
        self.package = package


# ---------------------------------------------------------------------------
# Confirmation modal
# ---------------------------------------------------------------------------


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "dismiss_false", "Cancel")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.message, id="dialog-message")
            with Center(id="dialog-buttons"):
                yield Button("Confirm", variant="error", id="btn-confirm")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")

    def action_dismiss_false(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Mixin: run an ADB action in a background thread, then pop screens
# ---------------------------------------------------------------------------


class ActionRunnerMixin:
    """Mixin for Screen subclasses. Runs ADB actions off the main thread."""

    @work(thread=True)
    def run_action_in_thread(
        self,
        action: Action,
        device: str,
        package: str,
        pop_count: int,
    ) -> None:
        try:
            message = adb.run_action(action, device, package)
        except adb.AdbError as e:
            self.app.call_from_thread(self.notify, str(e), severity="error")
            return

        def on_done() -> None:
            for _ in range(pop_count):
                self.app.pop_screen()
            self.app.notify(message)

        self.app.call_from_thread(on_done)

    def _execute_action(
        self, action: Action, device: str, package: str, pop_count: int
    ) -> None:
        if action == Action.UNINSTALL:

            def on_confirm(confirmed: bool) -> None:
                if confirmed:
                    self.run_action_in_thread(action, device, package, pop_count)

            self.app.push_screen(ConfirmScreen(f"Uninstall '{package}'?"), on_confirm)
        else:
            self.run_action_in_thread(action, device, package, pop_count)


# ---------------------------------------------------------------------------
# Screen: device list
# ---------------------------------------------------------------------------


class DeviceScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield LoadingIndicator(id="loading")
        yield ListView(id="device-list")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Select a device"
        self.load_devices()

    @work(thread=True)
    def load_devices(self) -> None:
        try:
            devices = adb.get_devices()
        except FileNotFoundError:
            self.app.call_from_thread(self._on_error, "adb not found — is it in PATH?")
            return
        except adb.AdbError as e:
            self.app.call_from_thread(self._on_error, str(e))
            return
        self.app.call_from_thread(self._populate, devices)

    def _populate(self, devices: list[str]) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        if not devices:
            self.notify("No devices connected — press R to refresh", severity="warning")
            return
        lv = self.query_one("#device-list", ListView)
        lv.clear()
        for device in devices:
            lv.append(DeviceItem(device))
        if len(devices) == 1:
            self.app.push_screen(ActionScreen(devices[0]))

    def _on_error(self, message: str) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        self.notify(message, severity="error")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, DeviceItem):
            self.app.push_screen(ActionScreen(event.item.device_id))

    def action_refresh(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#device-list", ListView).clear()
        self.load_devices()

    def action_quit(self) -> None:
        self.app.exit()


# ---------------------------------------------------------------------------
# Screen: action menu
# ---------------------------------------------------------------------------


class ActionScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, device: str) -> None:
        super().__init__()
        self.device = device

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(*[ActionItem(a) for a in Action], id="action-list")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = adb.format_device(self.device)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ActionItem):
            self.app.push_screen(PackageInputScreen(self.device, event.item.action))


# ---------------------------------------------------------------------------
# Screen: package name input
# ---------------------------------------------------------------------------


class PackageInputScreen(ActionRunnerMixin, Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, device: str, action: Action) -> None:
        super().__init__()
        self.device = device
        self.action = action

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Enter partial package name:", id="instruction")
        yield Input(placeholder="e.g. chrome, spotify", id="package-input")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{adb.format_device(self.device)} › {self.action.value}"
        self.query_one("#package-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        partial = event.value.strip()
        if partial:
            self.search_packages(partial)

    @work(thread=True)
    def search_packages(self, partial: str) -> None:
        try:
            packages = adb.get_packages(self.device, partial)
        except adb.AdbError as e:
            self.app.call_from_thread(self.notify, str(e), severity="error")
            return
        self.app.call_from_thread(self._on_packages_found, packages, partial)

    def _on_packages_found(self, packages: list[str], partial: str) -> None:
        if not packages:
            self.notify(f"No packages matching '{partial}'", severity="error")
            return
        if len(packages) == 1:
            self._execute_action(self.action, self.device, packages[0], pop_count=1)
        else:
            self.app.push_screen(
                PackageSelectScreen(self.device, self.action, packages)
            )


# ---------------------------------------------------------------------------
# Screen: package selection (when multiple packages match)
# ---------------------------------------------------------------------------


class PackageSelectScreen(ActionRunnerMixin, Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, device: str, action: Action, packages: list[str]) -> None:
        super().__init__()
        self.device = device
        self.action = action
        self.packages = packages

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(*[PackageItem(pkg) for pkg in self.packages], id="package-list")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{adb.format_device(self.device)} › {self.action.value}"

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, PackageItem):
            self._execute_action(
                self.action, self.device, event.item.package, pop_count=2
            )


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------


class AdbTuiApp(App):
    TITLE = "ADB TUI"
    CSS_PATH = "app.tcss"

    def on_mount(self) -> None:
        self.push_screen(DeviceScreen())
