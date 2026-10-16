from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.runners.part_a import main

if __name__=="__main__":main()
