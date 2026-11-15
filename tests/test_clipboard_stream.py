"""Clipboard MIME negotiation and PNG normalization (pure Python)."""
import unittest

from snapmark.clipboard_images import (PNG_MAGIC, clipboard_image_state,
                                       image_mime_types, image_to_png)


class FakeFormats:
    def __init__(self, mimes=(), gtypes=()):
        self._mimes = tuple(mimes)
        self._gtypes = tuple(gtypes)

    def get_mime_types(self):
        return self._mimes

    def get_gtypes(self):
        return self._gtypes

    def contain_gtype(self, gtype):
        return gtype in self._gtypes


class MimeNegotiationTests(unittest.TestCase):
    def test_prefers_png_then_known_image_formats(self):
        mimes = ['text/html', 'image/webp', 'image/png', 'text/plain', 'image/jpeg']
        self.assertEqual(image_mime_types(FakeFormats(mimes)),
                         ('image/png', 'image/jpeg', 'image/webp'))

    def test_text_html_and_uri_lists_offer_no_image_stream(self):
        for mimes in (['text/plain'], ['text/html', 'text/plain'],
                      ['text/uri-list', 'application/x-gnome-copied-files']):
            self.assertEqual(image_mime_types(FakeFormats(mimes)), ())

    def test_unknown_image_mimes_are_still_readable(self):
        self.assertEqual(image_mime_types(FakeFormats(['image/x-custom'])),
                         ('image/x-custom',))

    def test_empty_or_broken_formats_are_safe(self):
        self.assertEqual(image_mime_types(None), ())
        self.assertEqual(image_mime_types(FakeFormats()), ())

    def test_original_state_classification_is_unchanged(self):
        self.assertEqual(clipboard_image_state(FakeFormats(['image/png'])), 'image')
        self.assertEqual(clipboard_image_state(FakeFormats(['text/plain'])), 'other')
        self.assertEqual(clipboard_image_state(None), 'empty')


class ImageToPngTests(unittest.TestCase):
    def test_png_payload_passes_through_unchanged(self):
        payload = PNG_MAGIC + b'clipboard-image-bytes'
        self.assertEqual(image_to_png(payload), payload)

    def test_empty_and_oversized_payloads_are_rejected(self):
        self.assertIsNone(image_to_png(b''))
        self.assertIsNone(image_to_png(b'x' * (32 * 1024 * 1024 + 1)))

    def test_undecodable_payload_is_rejected_without_raising(self):
        self.assertIsNone(image_to_png(b'not-an-image'))


if __name__ == '__main__':
    unittest.main()
