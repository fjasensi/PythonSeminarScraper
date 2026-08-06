import unittest
import logging

import main
from seminar import Seminar


class PriceMonitoringTests(unittest.TestCase):
    def setUp(self):
        main.discount_alert_mode = "increase_over_threshold"
        main.min_discount_percentage = 20
        main.price_alert_threshold = 550

    def test_extracts_price_from_html(self):
        content = "<div>Precio: <strong>499,50€</strong></div>"

        self.assertEqual(main.extractPrice(content), 499.5)

    def test_uses_reduced_price_if_page_contains_two_prices(self):
        content = "<div>Precio: 550€</div><div>Precio: 440€</div>"

        self.assertEqual(main.extractPrice(content), 440)

    def test_notifies_only_when_price_drops_below_threshold(self):
        seminar = Seminar("Test seminar", "https://example.invalid/seminar")

        should_notify, _ = main.evaluateSeminar("Precio: 550€", seminar)
        self.assertFalse(should_notify)

        should_notify, message = main.evaluateSeminar("Precio: 500€", seminar)
        self.assertTrue(should_notify)
        self.assertIn("price dropped from 550€ to 500€", message)

        should_notify, _ = main.evaluateSeminar("Precio: 500€", seminar)
        self.assertFalse(should_notify)

        should_notify, message = main.evaluateSeminar("Precio: 450€", seminar)
        self.assertTrue(should_notify)
        self.assertIn("price dropped from 500€ to 450€", message)

    def test_percentage_alert_still_works(self):
        seminar = Seminar("Test seminar", "https://example.invalid/seminar")

        should_notify, message = main.evaluateSeminar(
            "Precio: 550€ Oferta: 25% de descuento",
            seminar,
        )

        self.assertTrue(should_notify)
        self.assertIn("discount is 25%", message)

    def test_percentage_can_span_html_tags(self):
        content = "<strong>30%</strong> <span>de descuento</span>"

        self.assertEqual(main.extractDiscountPercentage(content), 30)


class CatalogDiscoveryTests(unittest.TestCase):
    def test_extracts_unique_catalog_links_and_ignores_other_pages(self):
        content = """
        <a href="/oferta-academica/first/">First</a>
        <a href="https://escueladehumanidades.unir.net/oferta-academica/first/#price">Duplicate</a>
        <a href="/oferta-academica/second/?source=home">Second</a>
        <a href="/oferta-academica/">Catalog</a>
        <a href="https://example.com/oferta-academica/external/">External</a>
        """

        self.assertEqual(
            main.extractCatalogSeminarUrls(content),
            [
                "https://escueladehumanidades.unir.net/oferta-academica/first/",
                "https://escueladehumanidades.unir.net/oferta-academica/second/",
            ],
        )

    def test_merges_txt_and_catalog_seminars_without_losing_price_state(self):
        tracked = [Seminar("Tracked", "https://example.com/oferta-academica/a/")]
        tracked[0].actual_price = 500
        catalog = [
            Seminar("Duplicate", "https://example.com/oferta-academica/a/#price"),
            Seminar("New", "https://example.com/oferta-academica/b/"),
        ]
        state = {main.normalizeSeminarUrl(tracked[0].url): tracked[0]}

        merged = main.mergeSeminars(tracked, catalog, state)

        self.assertEqual(len(merged), 2)
        self.assertIs(merged[0], tracked[0])
        self.assertEqual(merged[0].actual_price, 500)

    def test_extracts_detail_page_heading(self):
        content = "<h1><span>El arte</span> de pensar</h1>"

        self.assertEqual(main.extractSeminarName(content), "El arte de pensar")


class LoggingTests(unittest.TestCase):
    def test_formatter_includes_madrid_timezone(self):
        formatter = main.TimezoneFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z",
            timezone_name="Europe/Madrid",
        )
        record = logging.LogRecord("test", logging.INFO, "", 0, "working", (), None)

        rendered = formatter.format(record)

        self.assertRegex(rendered, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (CET|CEST) INFO working$")


if __name__ == "__main__":
    unittest.main()
