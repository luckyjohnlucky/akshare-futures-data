#!/bin/bash

set -e
set -u

# Helper function to check if a string contains another string
contains() {
    local string="$1"
    local substring="$2"
    [[ "$string" == *"$substring"* ]]
}

test_scenario_1() {
    echo "Test 1: Nine commodity futures daily and minute files exist - all collected"
    
    # Create test files directly in current directory
    rm -rf output
    mkdir -p output
    
    # Create V0-V9 _daily_bars.csv and _minute_bars.csv (9 symbols × 2 files = 18 files)
    local symbols=(V0 TA0 MA0 PP0 L0 SA0 FG0 RB0 HC0)
    for symbol in "${symbols[@]}"; do
        touch "output/${symbol}_daily_bars.csv"
        touch "output/${symbol}_minute_bars.csv"
    done
    
    # Simulate FILES variable logic from collect.yml using array
    local FILES=()
    for symbol in V0 TA0 MA0 PP0 L0 SA0 FG0 RB0 HC0; do
        if [ -f "output/${symbol}_minute_bars.csv" ]; then
            FILES+=("output/${symbol}_minute_bars.csv")
        fi
        if [ -f "output/${symbol}_daily_bars.csv" ]; then
            FILES+=("output/${symbol}_daily_bars.csv")
        fi
    done
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    # Count files
    local file_count=${#FILES[@]}
    
    if [ $file_count -eq 18 ]; then
        echo "Test 1: PASS - All 18 files collected"
        return 0
    else
        echo "Test 1: FAIL - Expected 18 files, got $file_count"
        return 1
    fi
}

test_scenario_2() {
    echo "Test 2: H11061 old daily bars legacy file is ignored"
    
    rm -rf output
    mkdir -p output
    touch "output/H11061_daily_bars.csv"
    
    local FILES=()
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    local has_legacy=0
    
    if [ $file_count -gt 0 ]; then
        for file in "${FILES[@]}"; do
            if contains "$file" "H11061_daily_bars.csv"; then
                ((has_legacy++))
            fi
        done
    fi

    if [ $file_count -eq 0 ] && [ $has_legacy -eq 0 ]; then
        echo "Test 2: PASS - Legacy H11061 daily bars ignored"
        return 0
    else
        echo "Test 2: FAIL - Expected legacy file to be ignored, got $file_count files (legacy count: $has_legacy)"
        return 1
    fi
}

test_scenario_3() {
    echo "Test 3: H11061 new index daily only"
    
    rm -rf output
    mkdir -p output
    touch "output/H11061_index_daily.csv"
    
    local FILES=()
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    
    if [ $file_count -eq 1 ] && contains "${FILES[0]}" "H11061_index_daily.csv"; then
        echo "Test 3: PASS - H11061 new index daily collected"
        return 0
    else
        echo "Test 3: FAIL - Expected H11061 new index daily"
        return 1
    fi
}

test_scenario_4() {
    echo "Test 4: H11061 minute bars only"
    
    rm -rf output
    mkdir -p output
    touch "output/H11061_minute_bars.csv"
    
    local FILES=()
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    
    if [ $file_count -eq 1 ] && contains "${FILES[0]}" "H11061_minute_bars.csv"; then
        echo "Test 4: PASS - H11061 minute bars collected"
        return 0
    else
        echo "Test 4: FAIL - Expected H11061 minute bars"
        return 1
    fi
}

test_scenario_5() {
    echo "Test 5: H11061 old daily file ignored, new index daily collected"
    
    rm -rf output
    mkdir -p output
    touch "output/H11061_daily_bars.csv"
    touch "output/H11061_index_daily.csv"
    
    local FILES=()
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    local has_daily=0
    local has_index=0
    
    for file in "${FILES[@]}"; do
        if contains "$file" "H11061_daily_bars.csv"; then
            ((has_daily++))
        elif contains "$file" "H11061_index_daily.csv"; then
            ((has_index++))
        fi
    done
    
    if [ $file_count -eq 1 ] && [ $has_daily -eq 0 ] && [ $has_index -eq 1 ]; then
        echo "Test 5: PASS - Only new index daily collected, old ignored"
        return 0
    else
        echo "Test 5: FAIL - Expected only new index daily, got $file_count files (legacy: $has_daily, index: $has_index)"
        return 1
    fi
}

test_scenario_6() {
    echo "Test 6: All H11061 file types, old ignored"
    
    rm -rf output
    mkdir -p output
    touch "output/H11061_daily_bars.csv"
    touch "output/H11061_index_daily.csv"
    touch "output/H11061_minute_bars.csv"
    
    local FILES=()
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    local has_daily=0
    local has_index=0
    local has_minute=0
    
    for file in "${FILES[@]}"; do
        if contains "$file" "H11061_daily_bars.csv"; then
            ((has_daily++))
        elif contains "$file" "H11061_index_daily.csv"; then
            ((has_index++))
        elif contains "$file" "H11061_minute_bars.csv"; then
            ((has_minute++))
        fi
    done
    
    if [ $file_count -eq 2 ] && [ $has_daily -eq 0 ] && [ $has_index -eq 1 ] && [ $has_minute -eq 1 ]; then
        echo "Test 6: PASS - Index and minute collected, old ignored"
        return 0
    else
        echo "Test 6: FAIL - Expected 2 files: index daily, minute bars (legacy: $has_daily)"
        return 1
    fi
}

test_scenario_7() {
    echo "Test 7: No files exist"
    
    rm -rf output
    mkdir -p output
    
    local FILES=()
    for symbol in V0 TA0 MA0 PP0 L0 SA0 FG0 RB0 HC0; do
        if [ -f "output/${symbol}_minute_bars.csv" ]; then
            FILES+=("output/${symbol}_minute_bars.csv")
        fi
        if [ -f "output/${symbol}_daily_bars.csv" ]; then
            FILES+=("output/${symbol}_daily_bars.csv")
        fi
    done
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    if [ ${#FILES[@]} -eq 0 ]; then
        echo "Test 7: PASS - No files exist, empty FILES array"
        return 0
    else
        echo "Test 7: FAIL - Expected empty FILES, got ${#FILES[@]} files"
        return 1
    fi
}

test_scenario_8() {
    echo "Test 8: Mixed file existence"
    
    rm -rf output
    mkdir -p output
    
    # Create only V0 and TA0 minute files
    touch "output/V0_minute_bars.csv"
    touch "output/TA0_minute_bars.csv"
    touch "output/V0_daily_bars.csv"
    
    # Create H11061 minute bars
    touch "output/H11061_minute_bars.csv"
    
    local FILES=()
    for symbol in V0 TA0 MA0 PP0 L0 SA0 FG0 RB0 HC0; do
        if [ -f "output/${symbol}_minute_bars.csv" ]; then
            FILES+=("output/${symbol}_minute_bars.csv")
        fi
        if [ -f "output/${symbol}_daily_bars.csv" ]; then
            FILES+=("output/${symbol}_daily_bars.csv")
        fi
    done
    if [ -f "output/H11061_index_daily.csv" ]; then
        FILES+=("output/H11061_index_daily.csv")
    fi
    if [ -f "output/H11061_minute_bars.csv" ]; then
        FILES+=("output/H11061_minute_bars.csv")
    fi
    
    local file_count=${#FILES[@]}
    
    if [ $file_count -eq 4 ]; then
        echo "Test 8: PASS - 4 existing files collected"
        return 0
    else
        echo "Test 8: FAIL - Expected 4 files, got $file_count"
        return 1
    fi
}

main() {
    echo "=== Testing Workflow Collect Logic ==="
    echo "Current directory: $(pwd)"
    echo
    
    local pass_count=0
    local total_count=8
    
    if test_scenario_1; then
        ((pass_count++))
    fi
    
    if test_scenario_2; then
        ((pass_count++))
    fi
    
    if test_scenario_3; then
        ((pass_count++))
    fi
    
    if test_scenario_4; then
        ((pass_count++))
    fi
    
    if test_scenario_5; then
        ((pass_count++))
    fi
    
    if test_scenario_6; then
        ((pass_count++))
    fi
    
    if test_scenario_7; then
        ((pass_count++))
    fi
    
    if test_scenario_8; then
        ((pass_count++))
    fi
    
    echo
    echo "=== Summary ==="
    echo "Passed: $pass_count/$total_count"
    
    if [ $pass_count -eq $total_count ]; then
        echo "All tests PASSED ✓"
        return 0
    else
        echo "Some tests FAILED ✗"
        return 1
    fi
}

main
