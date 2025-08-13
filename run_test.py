#!/usr/bin/env python3
"""
Script to run the ID button tests
"""

import sys
import os
import subprocess

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Run the test
if __name__ == '__main__':
    test_file = os.path.join(os.path.dirname(__file__), 'src', 'tests', 'test_id_button.py')
    
    print("Running ID Button Tests...")
    print("=" * 50)
    
    try:
        # Run using unittest module
        result = subprocess.run([
            sys.executable, '-m', 'unittest', 
            'src.tests.test_id_button', '-v'
        ], cwd=os.path.dirname(__file__), capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        print(f"Return code: {result.returncode}")
        
    except Exception as e:
        print(f"Error running tests: {e}")
        
        # Fallback: try to import and run directly
        print("\nTrying direct import...")
        try:
            from src.tests.test_id_button import TestIDButtonBehavior
            import unittest
            
            suite = unittest.TestLoader().loadTestsFromTestCase(TestIDButtonBehavior)
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            
            if result.wasSuccessful():
                print("\n✅ All tests passed!")
            else:
                print(f"\n❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
                
        except Exception as e2:
            print(f"Direct import also failed: {e2}")