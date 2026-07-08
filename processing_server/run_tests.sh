#!/bin/bash

# Test runner script for processing_server
# Usage: ./run_tests.sh [option]

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    print_error "pytest not installed. Installing..."
    pip install pytest pytest-cov pytest-xdist pytest-timeout
fi

# Default to all tests
TEST_MODE=${1:-all}

case $TEST_MODE in
    all)
        print_header "Running ALL tests"
        pytest tests/ -v
        ;;
    quick)
        print_header "Running QUICK tests (fast checks only)"
        pytest tests/ -v -m "not slow" --timeout=10
        ;;
    unit)
        print_header "Running UNIT tests"
        pytest tests/test_yolo_inference.py tests/test_crowd_inference.py tests/test_transreid.py -v
        ;;
    yolo)
        print_header "Running YOLO detection tests"
        pytest tests/test_yolo_inference.py -v
        ;;
    crowd)
        print_header "Running DM-Count crowd inference tests"
        pytest tests/test_crowd_inference.py -v
        ;;
    reid)
        print_header "Running TransReID embedding tests"
        pytest tests/test_transreid.py -v
        ;;
    coverage)
        print_header "Running tests with COVERAGE report"
        pytest tests/ --cov=processing_server --cov-report=html --cov-report=term-missing
        print_success "Coverage report generated in htmlcov/index.html"
        ;;
    parallel)
        print_header "Running tests in PARALLEL"
        pytest tests/ -v -n auto
        ;;
    performance)
        print_header "Running PERFORMANCE benchmarks"
        pytest tests/ -v -m "performance"
        ;;
    slow)
        print_header "Running SLOW/Integration tests"
        pytest tests/ -v -m "integration or slow"
        ;;
    debug)
        print_header "Running tests in DEBUG mode"
        pytest tests/ -v -s --tb=long --pdb
        ;;
    watch)
        print_header "Watching tests (requires pytest-watch)"
        pip install pytest-watch > /dev/null 2>&1 || {
            print_error "pytest-watch not installed"
            exit 1
        }
        ptw tests/ -- -v
        ;;
    lint)
        print_header "Running linting on tests"
        if command -v pylint &> /dev/null; then
            pylint tests/
        else
            print_warning "pylint not installed, skipping"
        fi
        ;;
    clean)
        print_header "Cleaning test artifacts"
        rm -rf __pycache__ .pytest_cache .coverage htmlcov *.pyc
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        print_success "Cleaned"
        ;;
    *)
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  all           Run all tests (default)"
        echo "  quick         Run fast tests only (skip slow)"
        echo "  unit          Run unit tests (YOLO, DM-Count, TransReID)"
        echo "  yolo          Run YOLO detection tests only"
        echo "  crowd         Run DM-Count crowd inference tests only"
        echo "  reid          Run TransReID embedding tests only"
        echo "  coverage      Run tests with coverage report (HTML)"
        echo "  parallel      Run tests in parallel for speed"
        echo "  performance   Run performance benchmarks only"
        echo "  slow          Run slow/integration tests"
        echo "  debug         Run with debugger (pdb)"
        echo "  watch         Watch for file changes and re-run tests"
        echo "  lint          Check code style"
        echo "  clean         Remove test artifacts"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh                # Run all tests"
        echo "  ./run_tests.sh quick          # Run fast tests"
        echo "  ./run_tests.sh yolo           # Test YOLO only"
        echo "  ./run_tests.sh coverage       # With coverage report"
        echo "  ./run_tests.sh parallel       # Parallel execution"
        exit 0
        ;;
esac

# Check exit code
if [ $? -eq 0 ]; then
    print_success "Tests passed!"
else
    print_error "Tests failed!"
    exit 1
fi
