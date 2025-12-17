#!/usr/bin/env python
"""
Simple verification script that checks code structure without requiring Django setup
"""

import ast
import os

def check_file_syntax(filepath):
    """Check if a Python file has valid syntax"""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
        return True, None
    except SyntaxError as e:
        return False, str(e)

def verify_class_methods(filepath, expected_classes):
    """Verify that expected classes and methods exist"""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())

        found_classes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                found_classes[node.name] = methods

        for class_name, expected_methods in expected_classes.items():
            if class_name not in found_classes:
                return False, f"Class {class_name} not found"

            for method in expected_methods:
                if method not in found_classes[class_name]:
                    return False, f"Method {method} not found in {class_name}"

        return True, None
    except Exception as e:
        return False, str(e)

def main():
    print("="*70)
    print("LEVEL 2 IMPLEMENTATION - STRUCTURE VERIFICATION")
    print("="*70)

    base_path = "apps/trading"
    all_passed = True

    # Test 1: Check syntax of all new files
    print("\n1. Syntax Verification")
    print("-" * 70)

    files_to_check = [
        "apps/trading/data_aggregator.py",
        "apps/trading/level2_analyzers.py",
        "apps/trading/level2_analyzers_part2.py",
        "apps/trading/level2_report_generator.py",
        "apps/trading/views_level2.py",
        "apps/trading/urls_level2.py",
        "apps/data/models.py",
    ]

    for filepath in files_to_check:
        valid, error = check_file_syntax(filepath)
        if valid:
            print(f"✅ {filepath}")
        else:
            print(f"❌ {filepath}: {error}")
            all_passed = False

    # Test 2: Verify class structures
    print("\n2. Class Structure Verification")
    print("-" * 70)

    class_checks = {
        "apps/trading/data_aggregator.py": {
            "TrendlyneDataAggregator": ["fetch_all_data", "get_fundamentals", "get_forecaster_data"]
        },
        "apps/trading/level2_analyzers.py": {
            "FinancialPerformanceAnalyzer": ["analyze"],
            "ValuationDeepDive": ["analyze"]
        },
        "apps/trading/level2_analyzers_part2.py": {
            "InstitutionalBehaviorAnalyzer": ["analyze"],
            "TechnicalDeepDive": ["analyze"],
            "RiskAssessment": ["analyze"]
        },
        "apps/trading/level2_report_generator.py": {
            "Level2ReportGenerator": ["generate_report", "calculate_conviction_score"]
        }
    }

    for filepath, expected_classes in class_checks.items():
        valid, error = verify_class_methods(filepath, expected_classes)
        if valid:
            print(f"✅ {filepath} - All classes and methods present")
        else:
            print(f"❌ {filepath}: {error}")
            all_passed = False

    # Test 3: Check that existing files weren't corrupted
    print("\n3. Existing File Integrity Check")
    print("-" * 70)

    existing_files = [
        "apps/trading/futures_analyzer.py",
        "apps/data/models.py",  # Should still have old models
    ]

    for filepath in existing_files:
        valid, error = check_file_syntax(filepath)
        if valid:
            print(f"✅ {filepath} - Still valid")
        else:
            print(f"❌ {filepath}: {error}")
            all_passed = False

    # Verify existing models still exist
    with open("apps/data/models.py", 'r') as f:
        models_content = f.read()
        existing_models = ['MarketData', 'ContractData', 'TLStockData', 'ContractStockData']
        for model in existing_models:
            if f"class {model}" in models_content:
                print(f"✅ Model {model} still exists")
            else:
                print(f"❌ Model {model} missing!")
                all_passed = False

    # Test 4: File size check (ensure nothing is empty)
    print("\n4. File Completeness Check")
    print("-" * 70)

    for filepath in files_to_check:
        size = os.path.getsize(filepath)
        if size > 100:  # At least 100 bytes
            print(f"✅ {filepath} ({size} bytes)")
        else:
            print(f"❌ {filepath} is too small ({size} bytes) - possibly empty")
            all_passed = False

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)

    if all_passed:
        print("✅ ALL CHECKS PASSED!")
        print("\nImplementation appears to be complete and correct.")
        print("\nNext steps:")
        print("1. Run: python manage.py makemigrations data")
        print("2. Run: python manage.py migrate")
        print("3. Add 'apps.trading.urls_level2' to main urls.py")
        print("4. Test API endpoints")
    else:
        print("❌ SOME CHECKS FAILED")
        print("\nPlease review the errors above.")

    return all_passed

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
