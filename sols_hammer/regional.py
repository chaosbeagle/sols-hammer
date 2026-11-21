"""Native lung inspection and regional typing."""
from .cli import POLICY
from pathology_tools.regional_bench import cli

def main():
    cli(POLICY,False)

if __name__ == '__main__':
    main()
