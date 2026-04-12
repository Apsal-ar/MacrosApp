"""Macro Tracker — application entry point.

Responsibilities:
- Initialise Supabase client and attach it to the Repository layer
- Construct the ScreenManager with all four screens
- Authenticate the user (email + password via Supabase Auth)
- Expose app-level state: current_user_id, unit_system
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any, Optional

# Kivy must be configured before any other kivy imports
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.clock import Clock                                    # noqa: E402
from kivy.core.window import Window                             # noqa: E402
from kivy.lang import Builder                                   # noqa: E402
from kivy.properties import NumericProperty                     # noqa: E402
from kivy.utils import platform as kivy_platform               # noqa: E402
from kivy.uix.screenmanager import ScreenManager, SlideTransition  # noqa: E402
from kivymd.app import MDApp                                    # noqa: E402
from kivymd.uix.screen import MDScreen                          # noqa: E402
from kivymd.uix.boxlayout import MDBoxLayout                   # noqa: E402

import config                                                   # noqa: E402
from services.repository import Repository                      # noqa: E402
from sync.cache_db import CacheDB                               # noqa: E402
from sync.sync_manager import SyncManager                        # noqa: E402
from utils.constants import (                                    # noqa: E402
    COLOR_PRIMARY,
    RGBA_BG,
    RGBA_PRIMARY,
    RGBA_SURFACE,
)
import widgets.macros_button  # noqa: F401, E402 — registers Macros*Button before Login KV
from screens.profile_screen import ProfileScreen                # noqa: E402
from screens.goals_screen import GoalsScreen                    # noqa: E402
from screens.tracker_screen import TrackerScreen                # noqa: E402
import screens.food_search_screen  # noqa: E402 — registers FoodSearchScreen KV rule
import screens.food_edit_screen  # noqa: E402 — registers FoodEditScreen KV rule
from screens.settings_screen import SettingsScreen              # noqa: E402
from widgets.macro_pie_chart import MacroPieChart               # noqa: E402
from widgets.macro_progress_bar import MacroProgressBar         # noqa: E402
from widgets.meal_card import MealCard                          # noqa: E402
from widgets.food_item_row import FoodItemRow                   # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Simulate iPhone SE screen on desktop (also the reference width for responsive text).
UI_REF_WIDTH = 390.0
# Width ratio is clamped to [UI_FONT_MIN_SCALE, UI_FONT_MAX_SCALE], then multiplied by
# UI_FONT_BASE_FACTOR. Max below ~1.15 avoids the old 1.9× blow-up on wide windows; the
# base factor dials overall size vs raw Material defaults (tracker, nav, profile KV, etc.).
UI_FONT_MIN_SCALE = 0.68
UI_FONT_MAX_SCALE = 1.08
UI_FONT_BASE_FACTOR = 0.92
Window.size = (390, 844)

# Global divider style: thin, full-width, dark neutral colour
Builder.load_string("""
#:import RGBA_LINE utils.constants.RGBA_LINE
<MDDivider>:
    size_hint_x: 1
    size_hint_y: None
    height: "0.5dp"
    theme_divider_color: "Custom"
    color: RGBA_LINE[:4]
""")

# Global card default: 12dp corner radius on all MDCards
Builder.load_string("""
#:import dp kivy.metrics.dp
<MDCard>:
    radius: [dp(12), dp(12), dp(12), dp(12)]
""")

# ---------------------------------------------------------------------------
# Login screen (inline KV)
# ---------------------------------------------------------------------------

Builder.load_string("""
<LoginScreen>:
    MDBoxLayout:
        orientation: "vertical"
        padding: ["24dp", "60dp", "24dp", "40dp"]
        spacing: "20dp"

        MDLabel:
            text: "Macro Tracker"
            font_style: "Display"
            role: "small"
            halign: "center"
            size_hint_y: None
            height: "80dp"

        MDLabel:
            text: "Track your nutrition, reach your goals"
            font_style: "Body"
            role: "medium"
            halign: "center"
            theme_text_color: "Secondary"
            size_hint_y: None
            height: "36dp"

        Widget:
            size_hint_y: 0.1

        MDTextField:
            id: email_field
            hint_text: "Email"
            input_type: "mail"

        MDTextField:
            id: password_field
            hint_text: "Password"
            password: True

        MDLabel:
            id: error_label
            text: ""
            theme_text_color: "Error"
            size_hint_y: None
            height: "24dp"
            halign: "center"

        MacrosFilledButton:
            on_release: app.login(root.ids.email_field.text, root.ids.password_field.text, root)

            MDButtonText:
                text: "Sign In"

        MacrosTextButton:
            on_release: app.sign_up(root.ids.email_field.text, root.ids.password_field.text, root)

            MDButtonText:
                text: "Create Account"

        Widget:
            size_hint_y: 1
""")


class LoginScreen(MDScreen):
    """Email/password login and sign-up screen."""
    name = "login"


# ---------------------------------------------------------------------------
# Bottom navigation shell
# ---------------------------------------------------------------------------

Builder.load_string("""
<AppShell>:
    MDBoxLayout:
        orientation: "vertical"

        ScreenManager:
            id: inner_sm
            TrackerScreen:
            ProfileScreen:
            GoalsScreen:
            SettingsScreen:
            FoodSearchScreen:
            FoodEditScreen:

        MDNavigationBar:
            id: nav_bar
            on_switch_tabs: app.switch_tab(args[1], args[2], args[3])

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "food-apple"
                MDNavigationItemLabel:
                    text: "Tracker"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "account"
                MDNavigationItemLabel:
                    text: "Profile"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "target"
                MDNavigationItemLabel:
                    text: "Goals"

            MDNavigationItem:
                MDNavigationItemIcon:
                    icon: "cog"
                MDNavigationItemLabel:
                    text: "Settings"
""")


class AppShell(MDScreen):
    """Outer shell screen containing the bottom navigation + inner ScreenManager."""
    name = "app"


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class MacroTrackerApp(MDApp):
    """Root Kivy application.

    App-level state:
        current_user_id (str): Authenticated user's profile UUID.
        unit_system (str): 'metric' | 'imperial', shared across all screens.
        version (str): Display version string.
    """

    current_user_id: str = ""
    unit_system: str = "metric"
    version: str = config.APP_VERSION

    #: Scales with window width on desktop; bound from KV as ``app.ui_font_scale``.
    ui_font_scale = NumericProperty(1.0)

    _theme_font_styles_base: Optional[dict[str, Any]] = None

    # Screen name → inner ScreenManager name mapping
    _TAB_SCREENS = ["tracker", "profile", "goals", "settings"]

    def build(self) -> ScreenManager:
        """Build and return the root ScreenManager.

        Returns:
            A ScreenManager containing the login and app shell screens.
        """
        self.theme_cls.on_colors = self._apply_custom_colors
        self.theme_cls.primary_palette = COLOR_PRIMARY
        self.theme_cls.theme_style = "Dark"

        cache_path = os.path.join(self.user_data_dir, "macros_cache.sqlite3")
        self._cache = CacheDB.get_instance(cache_path)
        Repository.set_cache(self._cache)

        # Supabase client (remote sync only; UI reads SQLite via repositories)
        self._supabase = self._init_supabase()
        Repository.set_client(self._supabase)

        self._sync: Optional[SyncManager] = None
        if self._supabase is not None:
            self._sync = SyncManager.init_instance(self._supabase, self._cache)

        root_sm = ScreenManager(transition=SlideTransition())
        root_sm.add_widget(LoginScreen())
        root_sm.add_widget(AppShell())
        root_sm.current = "login"

        return root_sm

    def _apply_custom_colors(self) -> None:
        """Override theme colors to match app palette (dark bg, teal accents)."""
        tc = self.theme_cls
        tc.backgroundColor = RGBA_BG
        tc.surfaceColor = RGBA_BG
        tc.surfaceDimColor = RGBA_BG
        tc.surfaceContainerColor = RGBA_SURFACE
        tc.surfaceContainerLowColor = RGBA_SURFACE
        tc.surfaceContainerLowestColor = RGBA_SURFACE
        tc.surfaceContainerHighColor = RGBA_SURFACE
        tc.surfaceContainerHighestColor = RGBA_SURFACE
        tc.primaryColor = RGBA_PRIMARY
        tc.surfaceTintColor = RGBA_PRIMARY

    def on_start(self) -> None:
        """Kivy lifecycle hook — auto-login for development when configured."""
        self._setup_responsive_ui_scale()
        if config.DEV_AUTO_LOGIN:
            Clock.schedule_once(self._auto_login, 0.3)

    def _setup_responsive_ui_scale(self) -> None:
        """Scale typography with window width on desktop.

        Kivy ``sp`` in properties does not track window size. KivyMD's theme
        stores ``font-size`` as pixels from ``sp()`` at import time, so changing
        :attr:`~kivy.metrics.Metrics.fontscale` does not resize Material text.

        We snapshot :attr:`theme_cls.font_styles` once, then on each resize set
        ``font-size`` to ``baseline * effective_scale``. The effective scale is
        derived from window width (capped so wide screens are not enlarged past
        the design baseline), then multiplied by :data:`UI_FONT_BASE_FACTOR`.
        KV that uses ``app.ui_font_scale`` uses the same factor for custom sizes.
        """
        if kivy_platform not in ("macosx", "win", "linux"):
            return
        Window.bind(on_resize=self._apply_responsive_ui_scale)
        Clock.schedule_once(self._apply_responsive_ui_scale, 0)

    def _apply_responsive_ui_scale(self, *args) -> None:
        if kivy_platform not in ("macosx", "win", "linux"):
            return
        w = float(Window.width)
        if w <= 1.0:
            return
        width_ratio = w / UI_REF_WIDTH
        width_ratio = max(UI_FONT_MIN_SCALE, min(UI_FONT_MAX_SCALE, width_ratio))
        scale = width_ratio * UI_FONT_BASE_FACTOR
        self.ui_font_scale = scale

        if self._theme_font_styles_base is None:
            self._theme_font_styles_base = copy.deepcopy(dict(self.theme_cls.font_styles))

        base_styles = self._theme_font_styles_base
        new_fs = copy.deepcopy(base_styles)
        for style_name in new_fs:
            for role_name in new_fs[style_name]:
                base_sz = base_styles[style_name][role_name]["font-size"]
                new_fs[style_name][role_name]["font-size"] = float(base_sz) * scale
        self.theme_cls.font_styles = new_fs

    def _auto_login(self, _dt: float) -> None:
        """Perform a silent Supabase login without showing the login screen.

        Tries saved session first, then DEV credentials, then login screen.
        """
        if self._restore_saved_session():
            return

        if self._supabase is not None and config.DEV_AUTO_LOGIN_PASSWORD:
            try:
                response = self._supabase.auth.sign_in_with_password(
                    {
                        "email": config.DEV_AUTO_LOGIN_EMAIL,
                        "password": config.DEV_AUTO_LOGIN_PASSWORD,
                    }
                )
                logger.info("Auto-login succeeded for %s", config.DEV_AUTO_LOGIN_EMAIL)
                self._persist_session(response)
                self._on_auth_success(response.user.id)
                return
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Auto-login failed: %s", exc)
        else:
            logger.warning("Auto-login disabled: missing Supabase client or password")

        self.root.current = "login"
        try:
            login_screen = self.root.get_screen("login")
            login_screen.ids.email_field.text = config.DEV_AUTO_LOGIN_EMAIL
            login_screen.ids.password_field.text = config.DEV_AUTO_LOGIN_PASSWORD or ""
            login_screen.ids.error_label.text = "Auto sign-in failed. Tap Sign In."
        except Exception:  # pylint: disable=broad-except
            pass

    def _init_supabase(self):
        """Create and return the Supabase client.

        Returns:
            supabase.Client instance, or None if credentials are placeholder values.
        """
        if "YOUR_PROJECT_ID" in config.SUPABASE_URL:
            logger.warning(
                "Supabase credentials not configured — running in offline-only mode. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY in config.py"
            )
            return None
        try:
            from supabase import create_client  # pylint: disable=import-outside-toplevel
            return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Supabase init failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self, email: str, password: str, login_screen: LoginScreen) -> None:
        """Attempt Supabase email/password sign-in.

        Args:
            email: User's email address.
            password: User's password.
            login_screen: The LoginScreen widget (used to show error messages).
        """
        if not email or not password:
            login_screen.ids.error_label.text = "Please enter email and password"
            return

        if self._supabase is None:
            self._enter_offline_demo(login_screen)
            return

        try:
            response = self._supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            user_id = response.user.id
            self._persist_session(response)
            self._on_auth_success(user_id, login_screen)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Login failed: %s", exc)
            login_screen.ids.error_label.text = "Sign in failed. Check your credentials."

    def sign_up(self, email: str, password: str, login_screen: LoginScreen) -> None:
        """Register a new user via Supabase Auth.

        Args:
            email: New user's email address.
            password: New user's password (min 6 chars enforced by Supabase).
            login_screen: The LoginScreen widget.
        """
        if not email or not password:
            login_screen.ids.error_label.text = "Please enter email and password"
            return

        if self._supabase is None:
            login_screen.ids.error_label.text = "Offline mode — cannot create accounts"
            return

        try:
            response = self._supabase.auth.sign_up({"email": email, "password": password})
            user_id = response.user.id
            self._persist_session(response)
            self._on_auth_success(user_id, login_screen)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Sign-up failed: %s", exc)
            login_screen.ids.error_label.text = "Sign up failed. Try a different email."

    def _on_auth_success(
        self,
        user_id: str,
        login_screen: Optional[LoginScreen] = None,
    ) -> None:
        """Called after successful auth — sync cache if needed, bootstrap profile, navigate."""
        self.current_user_id = user_id
        if login_screen is not None:
            login_screen.ids.error_label.text = ""

        self._cache.set_active_user(user_id)
        if self._sync is not None:
            self._sync.set_profile_id(user_id)

        empty = self._cache.is_cache_empty_for_user(user_id)
        blocking = empty and self._supabase is not None and self._sync is not None

        if blocking:
            if login_screen is not None:
                login_screen.ids.error_label.text = "Syncing data…"

            def work() -> None:
                try:
                    self._sync.full_sync()
                except Exception as exc:  # pylint: disable=broad-except
                    logger.debug("Initial full_sync: %s", exc)
                Clock.schedule_once(
                    lambda _dt: self._complete_auth_startup(login_screen, user_id, False),
                    0,
                )

            threading.Thread(target=work, daemon=True).start()
            return

        self._complete_auth_startup(login_screen, user_id, True)

    def _complete_auth_startup(
        self,
        login_screen: Optional[LoginScreen],
        user_id: str,
        background_full_sync: bool,
    ) -> None:
        """Bootstrap profile, go to tracker, periodic sync; optional background full_sync."""
        if login_screen is not None:
            login_screen.ids.error_label.text = ""
        try:
            self._ensure_profile_exists(user_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Profile bootstrap skipped: %s", exc)

        self.root.current = "app"
        try:
            app_shell = self.root.get_screen("app")
            app_shell.ids.inner_sm.current = "tracker"
        except Exception:  # pylint: disable=broad-except
            pass

        if self._sync is not None:
            self._sync.schedule(30.0)
            if background_full_sync and self._supabase is not None:
                threading.Thread(target=self._sync.full_sync, daemon=True).start()

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    @property
    def _session_file(self) -> str:
        return os.path.join(self.user_data_dir, "supabase_session.json")

    def _persist_session(self, auth_response: object) -> None:
        """Persist Supabase access + refresh tokens for future auto-login."""
        try:
            session = getattr(auth_response, "session", None)
            if session is None:
                return
            access_token = getattr(session, "access_token", None)
            refresh_token = getattr(session, "refresh_token", None)
            if not access_token or not refresh_token:
                return
            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"access_token": access_token, "refresh_token": refresh_token},
                    f,
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not persist auth session: %s", exc)

    def _restore_saved_session(self) -> bool:
        """Restore previously saved session and authenticate silently."""
        if self._supabase is None:
            return False
        try:
            if not os.path.exists(self._session_file):
                return False
            with open(self._session_file, "r", encoding="utf-8") as f:
                tokens = json.load(f)
            response = self._supabase.auth.set_session(
                tokens.get("access_token"),
                tokens.get("refresh_token"),
            )
            if not response or not getattr(response, "user", None):
                return False
            logger.info("Session restore succeeded for %s", response.user.id)
            self._persist_session(response)
            self._on_auth_success(response.user.id)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Session restore failed: %s", exc)
            self._clear_saved_session()
            return False

    def _clear_saved_session(self) -> None:
        try:
            if os.path.exists(self._session_file):
                os.remove(self._session_file)
        except Exception:  # pylint: disable=broad-except
            pass

    def _enter_offline_demo(self, login_screen: LoginScreen) -> None:
        """Show a message that network is required — offline mode is disabled."""
        login_screen.ids.error_label.text = "Network connection required"

    def _ensure_profile_exists(self, user_id: str) -> None:
        """Create a bare profile row in Supabase if one doesn't exist yet.

        Args:
            user_id: The newly authenticated user's UUID.
        """
        from services.repository import ProfileRepository, GoalsRepository  # noqa: PLC0415
        from models.user import Profile, Goals                              # noqa: PLC0415
        import time as _time                                                # noqa: PLC0415

        profile_repo = ProfileRepository()
        if profile_repo.get(user_id) is None:
            profile_repo.save(Profile(id=user_id, email="", updated_at=_time.time()))

        goals_repo = GoalsRepository()
        if goals_repo.get_for_profile(user_id) is None:
            goals_repo.save(Goals(
                id=Repository.new_id(),
                profile_id=user_id,
                updated_at=_time.time(),
            ))

    # ------------------------------------------------------------------
    # Bottom tab navigation
    # ------------------------------------------------------------------

    def switch_tab(self, item: object, item_icon: str, item_text: str) -> None:
        """Switch the inner ScreenManager to the tapped tab's screen.

        Args:
            item: The MDNavigationItem that was activated.
            item_icon: Icon name string (unused).
            item_text: Display label of the tab, e.g. 'Tracker'.
        """
        try:
            app_shell = self.root.get_screen("app")
            inner_sm: ScreenManager = app_shell.ids.inner_sm
            screen_name = item_text.lower()
            if screen_name in self._TAB_SCREENS:
                inner_sm.current = screen_name
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Tab switch failed: %s", exc)


if __name__ == "__main__":
    MacroTrackerApp().run()
