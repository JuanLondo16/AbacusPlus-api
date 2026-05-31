import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
print(f"\n[conftest] inserting {root} into sys.path")
sys.path.insert(0, root)
print(f"[conftest] sys.path[:3] = {sys.path[:3]}")
