import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qti_converter.browser_bridge import handle_request
from qti_converter.questions import ValidationError
from qti_converter.template import write_template


class BrowserBridgeTests(unittest.TestCase):
    def test_preview_and_download_use_the_same_validated_bank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_template(root / 'Banco_de_prueba.csv')
            common = {'input_path': str(source), 'filename': source.name}
            preview = json.loads(handle_request(json.dumps(common | {'action': 'analyze'})))
            self.assertEqual(preview['count'], 6)
            self.assertEqual(set(preview['types']), {'mc', 'ma', 'tf', 'short', 'blank', 'essay'})
            self.assertEqual(preview['suggested_title'], 'Banco De Prueba')
            for version in ('1.2', '2.1'):
                result = json.loads(handle_request(json.dumps(common | {
                    'action': 'generate', 'destination': str(root / 'output'),
                    'title': 'Cuestionario web', 'format': version,
                })))
                self.assertEqual(result['count'], preview['count'])
                with zipfile.ZipFile(result['path']) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn('imsmanifest.xml', archive.namelist())

    def test_invalid_csv_returns_a_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'invalid.csv'
            source.write_text('tipo,pregunta,a,b,correcta\nmc,Una pregunta,Uno,Dos,d\n', encoding='utf-8')
            with self.assertRaises(ValidationError):
                handle_request(json.dumps({'action': 'analyze', 'input_path': str(source), 'filename': source.name}))


if __name__ == '__main__':
    unittest.main()
