#!/usr/bin/env python
"""Test runner script for the payment system test suite.
Runs tests by category and generates reports.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and report results"""
    print(f"\n{'=' * 70}")
    print(f"📋 {description}")
    print(f"{'=' * 70}")
    print(f"$ {' '.join(cmd)}")
    print("-" * 70)

    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode == 0


def main():
    """Run all test suites"""
    backend_dir = Path(__file__).parent.parent

    print("""
╔════════════════════════════════════════════════════════════════════╗
║        CareBank Payment System - Test Suite Runner              ║
║                                                                    ║
║  This script runs all payment system tests organized by type      ║
║  - Unit tests: Individual service testing                         ║
║  - Integration tests: API endpoint testing                        ║
║  - E2E tests: End-to-end workflow testing                         ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Change to backend directory
    import os

    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))

    all_passed = True

    # 1. Run unit tests
    print("\n" + "=" * 70)
    print("🧪 UNIT TESTS - Testing individual service functions")
    print("=" * 70)

    if not run_command(
        [sys.executable, "-m", "pytest", "-v", "-m", "unit", "--tb=short"],
        "Running unit tests",
    ):
        all_passed = False

    # 2. Run integration tests
    print("\n" + "=" * 70)
    print("🔗 INTEGRATION TESTS - Testing API endpoints")
    print("=" * 70)

    if not run_command(
        [sys.executable, "-m", "pytest", "-v", "-m", "integration", "--tb=short"],
        "Running integration tests",
    ):
        all_passed = False

    # 3. Run E2E tests
    print("\n" + "=" * 70)
    print("🎯 END-TO-END TESTS - Testing complete workflows")
    print("=" * 70)

    if not run_command(
        [sys.executable, "-m", "pytest", "-v", "-m", "e2e", "--tb=short"],
        "Running E2E tests",
    ):
        all_passed = False

    # 4. Generate coverage report
    print("\n" + "=" * 70)
    print("📊 COVERAGE REPORT - Code coverage analysis")
    print("=" * 70)

    run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=app",
            "--cov-report=term-missing",
            "tests/",
        ],
        "Generating coverage report",
    )

    # 5. Final summary
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ All test suites passed!")
    else:
        print("❌ Some tests failed. Review output above.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
