import unittest
import requests

import os, stat
import tempfile
import shutil
import platform
import time

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from requests_file import FileAdapter

class FileRequestTestCase(unittest.TestCase):
    def setUp(self):
        self._session = requests.Session()
        self._session.mount("file://", FileAdapter())

    def _pathToURL(self, path):
        """Convert a filesystem path to a URL path"""
        urldrive, urlpath = os.path.splitdrive(path)

        # Split the path on the os spearator and recombine it with / as the
        # separator. There probably aren't any OS's that allow / as a path
        # component, but just in case, encode any remaining /'s.
        urlsplit = (part.replace("/", "%2F") for part in urlpath.split(os.sep))
        urlpath = "/".join(urlsplit)

        # Encode /'s in the drive for the imaginary case where that can be a thing
        urldrive = urldrive.replace("/", "%2F")

        # Add the leading /. If there is a drive component, this needs to be
        # placed before the drive.
        urldrive = "/" + urldrive

        return urldrive + urlpath

    def test_fetch_regular(self):
        # Fetch this file using requests
        with open(__file__, "rb") as f:
            testdata = f.read()
        response = self._session.get(
            "file://%s" % self._pathToURL(os.path.abspath(__file__))
        )

        self.assertEqual(response.status_code, requests.codes.ok)
        self.assertEqual(response.headers["Content-Length"], len(testdata))
        self.assertEqual(response.content, testdata)

        response.close()

    def test_fetch_missing(self):
        # Fetch a file that (hopefully) doesn't exist, look for a 404
        response = self._session.get("file:///no/such/path")
        self.assertEqual(response.status_code, requests.codes.not_found)
        self.assertTrue(response.text)
        response.close()

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "Skipping permissions test since running as root",
    )
    def test_fetch_no_access(self):
        # Create a file and remove read permissions, try to get a 403
        # probably doesn't work on windows
        with tempfile.NamedTemporaryFile() as tmp:
            os.chmod(tmp.name, 0)
            response = self._session.get(
                "file://%s" % self._pathToURL(os.path.abspath(tmp.name))
            )

            self.assertEqual(response.status_code, requests.codes.forbidden)
            self.assertTrue(response.text)

            response.close()

    @unittest.skipIf(platform.system() == "Windows", "skipping locale test on windows")
    def test_fetch_missing_localized(self):
        # Make sure translated error messages don't cause any problems
        import locale

        saved_locale = locale.setlocale(locale.LC_MESSAGES, None)
        try:
            locale.setlocale(locale.LC_MESSAGES, "ru_RU.UTF-8")
            response = self._session.get("file:///no/such/path")
            self.assertEqual(response.status_code, requests.codes.not_found)
            self.assertTrue(response.text)
            response.close()
        except locale.Error:
            unittest.SkipTest("ru_RU.UTF-8 locale not available")
        finally:
            locale.setlocale(locale.LC_MESSAGES, saved_locale)

    def test_head(self):
        # Check that HEAD returns the content-length
        testlen = os.stat(__file__).st_size
        response = self._session.head(
            "file://%s" % self._pathToURL(os.path.abspath(__file__))
        )

        self.assertEqual(response.status_code, requests.codes.ok)
        self.assertEqual(response.headers["Content-Length"], testlen)

        response.close()

    def test_fetch_post(self):
        # Make sure that non-GET methods are rejected
        self.assertRaises(
            ValueError,
            self._session.post,
            ("file://%s" % self._pathToURL(os.path.abspath(__file__))),
        )

    def test_fetch_nonlocal(self):
        # Make sure that network locations are rejected
        self.assertRaises(
            ValueError,
            self._session.get,
            ("file://example.com%s" % self._pathToURL(os.path.abspath(__file__))),
        )
        self.assertRaises(
            ValueError,
            self._session.get,
            ("file://localhost:8080%s" % self._pathToURL(os.path.abspath(__file__))),
        )

        # localhost is ok, though
        with open(__file__, "rb") as f:
            testdata = f.read()
        response = self._session.get(
            "file://localhost%s" % self._pathToURL(os.path.abspath(__file__))
        )
        self.assertEqual(response.status_code, requests.codes.ok)
        self.assertEqual(response.content, testdata)
        response.close()

    def test_funny_names(self):
        testdata = "yo wassup man\n".encode("ascii")
        tmpdir = tempfile.mkdtemp()

        try:
            with open(os.path.join(tmpdir, "spa ces"), "w+b") as space_file:
                space_file.write(testdata)
                space_file.flush()
                response = self._session.get(
                    "file://%s/spa%%20ces" % self._pathToURL(tmpdir)
                )
                self.assertEqual(response.status_code, requests.codes.ok)
                self.assertEqual(response.content, testdata)
                response.close()

            with open(os.path.join(tmpdir, "per%cent"), "w+b") as percent_file:
                percent_file.write(testdata)
                percent_file.flush()
                response = self._session.get(
                    "file://%s/per%%25cent" % self._pathToURL(tmpdir)
                )
                self.assertEqual(response.status_code, requests.codes.ok)
                self.assertEqual(response.content, testdata)
                response.close()

            # percent-encoded directory separators should be rejected
            with open(os.path.join(tmpdir, "badname"), "w+b") as bad_file:
                response = self._session.get(
                    "file://%s%%%Xbadname" % (self._pathToURL(tmpdir), ord(os.sep))
                )
                self.assertEqual(response.status_code, requests.codes.not_found)
                response.close()

        finally:
            shutil.rmtree(tmpdir)

    def test_close(self):
        # Open a request for this file
        response = self._session.get(
            "file://%s" % self._pathToURL(os.path.abspath(__file__))
        )

        # Try closing it
        response.close()

    def test_missing_close(self):
        # Make sure non-200 responses can be closed
        response = self._session.get("file:///no/such/path")
        response.close()

    @unittest.skipIf(platform.system() != "Windows", "skipping windows URL test")
    def test_windows_legacy(self):
        """Test |-encoded drive characters on Windows"""
        with open(__file__, "rb") as f:
            testdata = f.read()

        drive, path = os.path.splitdrive(os.path.abspath(__file__))
        response = self._session.get(
            "file:///%s|%s" % (drive[:-1], path.replace(os.sep, "/"))
        )
        self.assertEqual(response.status_code, requests.codes.ok)
        self.assertEqual(response.headers["Content-Length"], len(testdata))
        self.assertEqual(response.content, testdata)
        response.close()
    
    def test_caching(self):
        # Test that caching works by accessing the same file twice
        file_path = os.path.abspath(__file__)
        url = f"file://{self._pathToURL(file_path)}"

        # First request
        start_time = time.time()
        response1 = self._session.get(url)
        first_request_time = time.time() - start_time

        # Second request (should be faster due to caching)
        start_time = time.time()
        response2 = self._session.get(url)
        second_request_time = time.time() - start_time

        self.assertEqual(response1.content, response2.content)
        self.assertLess(second_request_time, first_request_time)

        response1.close()
        response2.close()

    def test_rate_limiting(self):
        # Test that rate limiting works
        file_path = os.path.abspath(__file__)
        url = f"file://{self._pathToURL(file_path)}"

        # Create a new session with a stricter rate limit
        rate_limited_session = requests.Session()
        rate_limited_session.mount("file://", FileAdapter(rate_limit=2, rate_interval=1))

        # First two requests should succeed
        response1 = rate_limited_session.get(url)
        response2 = rate_limited_session.get(url)

        self.assertEqual(response1.status_code, requests.codes.ok)
        self.assertEqual(response2.status_code, requests.codes.ok)

        # Third request should fail due to rate limiting
        with self.assertRaises(ValueError) as cm:
            rate_limited_session.get(url)

        self.assertIn("Rate limit exceeded", str(cm.exception))

        response1.close()
        response2.close()