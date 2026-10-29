from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qti_converter.template import write_template

write_template(Path(sys.argv[1]))
