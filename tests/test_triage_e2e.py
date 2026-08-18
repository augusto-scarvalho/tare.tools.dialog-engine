"""Playwright End-to-End Test Suite for Watson Dialog Triage and Wiki Console."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML_URI = (ROOT / "triage_viewer.html").as_uri()


class TriageConsoleE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        # Launch Chromium headless
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.page = self.context.new_page()
        self.page.goto(HTML_URI)

    def tearDown(self) -> None:
        self.context.close()

    def test_app_loads_and_displays_header(self) -> None:
        title = self.page.title()
        self.assertIn("tare.tools", title)
        header = self.page.locator(".brand-logo")
        self.assertTrue(header.is_visible())
        self.assertIn("tare.tools", header.inner_text())

    def test_global_tab_navigation(self) -> None:
        # 1. Triage Tab (Active by default)
        self.assertTrue(self.page.locator("#view-triage").is_visible())

        # 2. Guia de Triagem
        self.page.locator("#tab-btn-guide").click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator("#view-triage-guide").is_visible())
        self.assertFalse(self.page.locator("#view-triage").is_visible())
        # Check TOC is visible
        self.assertTrue(self.page.locator("#view-triage-guide .wiki-toc-sidebar:visible").is_visible())
        self.assertTrue(self.page.locator("#view-triage-guide .wiki-content-pane:visible").is_visible())

        # 3. Manual de Uso
        self.page.locator("#tab-btn-manual").click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator("#view-manual").is_visible())
        self.assertTrue(self.page.locator("#view-manual .wiki-toc-sidebar:visible").is_visible())

        # 4. Regras IBM
        self.page.locator("#tab-btn-rules").click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator("#view-ibm-rules").is_visible())

        # 5. Arquitetura
        self.page.locator("#tab-btn-arch").click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator("#view-arch").is_visible())

        # Switch back to Triage
        self.page.locator("#tab-btn-triage").click()
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator("#view-triage").is_visible())

    def test_triage_filtering_and_search(self) -> None:
        cards = self.page.locator(".issue-card")
        initial_count = cards.count()
        self.assertGreater(initial_count, 0)

        # Filter by Error
        self.page.locator("#filter-sev-error").click()
        self.page.wait_for_timeout(100)
        error_count = self.page.locator(".issue-card").count()
        self.assertEqual(error_count, 2)

        # Search filter
        self.page.locator("#filter-sev-all").click()
        search_box = self.page.locator("#search-input")
        search_box.fill("sys_number_zero_handler")
        self.page.wait_for_timeout(100)
        search_results = self.page.locator(".issue-card").count()
        self.assertEqual(search_results, 19)

        # Clear search
        search_box.fill("")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator(".issue-card").count(), initial_count)

    def test_triage_button_actions_and_persistence(self) -> None:
        first_card = self.page.locator(".issue-card").first
        bug_btn = first_card.locator("button:has-text('Bug Confirmado')")
        
        # Click Bug Confirmado
        bug_btn.click()
        self.page.wait_for_timeout(100)
        self.assertIn("active-bug", bug_btn.get_attribute("class"))
        self.assertIn("triage-bug", first_card.get_attribute("class"))

        # Check sidebar count updated
        bug_filter_count = self.page.locator("#count-status-bug").inner_text()
        self.assertEqual(bug_filter_count, "1")

        # Type reviewer notes
        notes_input = first_card.locator("textarea.notes-input")
        notes_input.fill("E2E Test Rationale: Defeito comprovado no slot")
        self.page.wait_for_timeout(100)

        # Reload page and verify localStorage persistence
        self.page.reload()
        self.page.wait_for_timeout(200)
        reloaded_card = self.page.locator(".issue-card").first
        reloaded_bug_btn = reloaded_card.locator("button:has-text('Bug Confirmado')")
        self.assertIn("active-bug", reloaded_bug_btn.get_attribute("class"))
        reloaded_notes = reloaded_card.locator("textarea.notes-input").input_value()
        self.assertEqual(reloaded_notes, "E2E Test Rationale: Defeito comprovado no slot")

        # Reset triage
        # Accept confirm dialog
        self.page.on("dialog", lambda dialog: dialog.accept())
        self.page.locator("#btn-reset-triage").click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator("#count-status-bug").inner_text(), "0")

    def test_node_inspection_drawer(self) -> None:
        # Find first card and click Inspecionar Nó
        first_card = self.page.locator(".issue-card").first
        inspect_btn = first_card.locator("button:has-text('Inspecionar Nó')")
        inspect_btn.click()
        self.page.wait_for_timeout(200)

        drawer = self.page.locator("#drawer")
        self.assertIn("open", drawer.get_attribute("class"))

        # Verify drawer elements
        drawer_uuid = self.page.locator("#drawer-node-uuid").inner_text()
        self.assertTrue(len(drawer_uuid) > 0)
        self.assertTrue(self.page.locator(".meta-grid").is_visible())
        self.assertTrue(self.page.locator(".raw-json-box").is_visible())

        # Close drawer
        self.page.locator("#btn-close-drawer").click()
        self.page.wait_for_timeout(200)
        self.assertNotIn("open", drawer.get_attribute("class"))

    def test_bilingual_switcher(self) -> None:
        # Default is PT-BR
        self.assertIn("Painel de Triagem", self.page.locator("#tab-btn-triage").inner_text())

        # Switch to English
        self.page.locator("#btn-lang-en").click()
        self.page.wait_for_timeout(150)
        self.assertIn("Triage Workspace", self.page.locator("#tab-btn-triage").inner_text())
        self.assertIn("Triage Guide", self.page.locator("#tab-btn-guide").inner_text())
        self.assertIn("CLI Manual", self.page.locator("#tab-btn-manual").inner_text())

        # Check that cards show translated buttons
        first_card = self.page.locator(".issue-card").first
        self.assertTrue(first_card.locator("button:has-text('Confirmed Bug')").is_visible())
        self.assertTrue(first_card.locator("button:has-text('False Positive')").is_visible())
        self.assertTrue(first_card.locator("button:has-text('Tech Debt')").is_visible())

        # Check that Guide tab in EN-US shows English docs
        self.page.locator("#tab-btn-guide").click()
        self.page.wait_for_timeout(150)
        self.assertTrue(self.page.locator("#view-triage-guide .lang-en").is_visible())
        self.assertFalse(self.page.locator("#view-triage-guide .lang-pt").is_visible())

        # Switch back to PT-BR
        self.page.locator("#btn-lang-pt").click()
        self.page.wait_for_timeout(150)
        self.assertTrue(self.page.locator("#view-triage-guide .lang-pt").is_visible())
        self.assertFalse(self.page.locator("#view-triage-guide .lang-en").is_visible())

    def test_theme_selector(self) -> None:
        theme_selector = self.page.locator("#themeSelector")
        self.assertTrue(theme_selector.is_visible())
        self.assertEqual(theme_selector.input_value(), "signal")

        # Switch to Dracula
        theme_selector.select_option("dracula")
        self.page.wait_for_timeout(100)
        bg_dracula = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-base').trim()")
        self.assertEqual(bg_dracula, "#282a36")

        # Switch to Tokyo Night
        theme_selector.select_option("tokyo_night")
        self.page.wait_for_timeout(100)
        bg_tokyo = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-base').trim()")
        self.assertEqual(bg_tokyo, "#1a1b26")

        # Switch to GitHub Light
        theme_selector.select_option("github_light")
        self.page.wait_for_timeout(100)
        bg_github = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-base').trim()")
        self.assertEqual(bg_github, "#ffffff")
        color_scheme = self.page.evaluate("document.documentElement.style.colorScheme")
        self.assertEqual(color_scheme, "light")

        # Reload and check persistence
        self.page.reload()
        self.page.wait_for_timeout(200)
        persisted_theme = self.page.locator("#themeSelector").input_value()
        self.assertEqual(persisted_theme, "github_light")

        # Switch back to Signal
        self.page.locator("#themeSelector").select_option("signal")
        self.page.wait_for_timeout(100)


if __name__ == "__main__":
    unittest.main()
