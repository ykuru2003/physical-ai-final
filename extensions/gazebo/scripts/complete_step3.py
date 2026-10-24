"""Compatibility command; implementation: validation/complete_step3.py."""
import sys
from validation.complete_step3 import main


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f'STEP 3 INCOMPLETE: {error}', file=sys.stderr)
        raise SystemExit(1)
