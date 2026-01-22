#!/bin/bash
# Pre-flight checks for deploying services to staging

set -e

echo "============================================================"
echo "  DEPLOYMENT PRE-FLIGHT CHECKS"
echo "============================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 - NOT FOUND"
        ((ERRORS++))
        return 1
    fi
}

check_syntax() {
    if python3 -m py_compile "$1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $1 - Syntax OK"
        return 0
    else
        echo -e "${RED}✗${NC} $1 - Syntax Error"
        ((ERRORS++))
        return 1
    fi
}

echo "1. Checking Dockerfiles..."
echo "-----------------------------------------------------------"
check_file "artemis/Dockerfile"
check_file "home-manager/Dockerfile"
check_file "vehicle-manager/Dockerfile"
check_file "meal-planner/Dockerfile"
echo ""

echo "2. Checking migration scripts..."
echo "-----------------------------------------------------------"
check_file "home-manager/migrate_db.py"
check_file "vehicle-manager/migrate_db.py"
check_file "meal-planner/migrate_db.py"
echo ""

echo "3. Checking main application files..."
echo "-----------------------------------------------------------"
check_file "artemis/artemis/api/main.py"
check_file "home-manager/main.py"
check_file "vehicle-manager/main.py"
check_file "meal-planner/main.py"
echo ""

echo "4. Checking common package..."
echo "-----------------------------------------------------------"
check_file "common/models/base.py"
check_file "common/database.py"
check_file "common/requirements.txt"
echo ""

echo "5. Checking requirements files..."
echo "-----------------------------------------------------------"
check_file "artemis/requirements.txt"
check_file "home-manager/requirements.txt"
check_file "vehicle-manager/requirements.txt"
check_file "meal-planner/requirements.txt"
echo ""

echo "6. Validating Python syntax..."
echo "-----------------------------------------------------------"
check_syntax "common/models/base.py"
check_syntax "common/database.py"
check_syntax "home-manager/main.py"
check_syntax "vehicle-manager/main.py"
check_syntax "meal-planner/main.py"
check_syntax "artemis/artemis/api/main.py"
echo ""

echo "7. Checking Docker build contexts..."
echo "-----------------------------------------------------------"
# Validate that Dockerfiles reference correct paths
for service in artemis home-manager vehicle-manager meal-planner; do
    if grep -q "COPY common/" "$service/Dockerfile" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $service/Dockerfile - References common package"
    else
        echo -e "${RED}✗${NC} $service/Dockerfile - Missing common package reference"
        ((ERRORS++))
    fi
done
echo ""

echo "8. Checking service URLs configuration..."
echo "-----------------------------------------------------------"
if grep -q "home_manager_url" artemis/artemis/core/settings.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Artemis settings.py - Configured"
else
    echo -e "${RED}✗${NC} Artemis settings.py - Missing service URLs"
    ((ERRORS++))
fi
echo ""

echo "9. Checking Artemis module integrations..."
echo "-----------------------------------------------------------"
for module in nutrition fitness assets; do
    if grep -q "ServiceClient" "artemis/artemis/modules/$module.py" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} ${module} module - Proxies to backend"
    else
        echo -e "${YELLOW}⚠${NC} ${module} module - Not yet integrated"
        ((WARNINGS++))
    fi
done
echo ""

echo "10. Validating service ports..."
echo "-----------------------------------------------------------"
check_port() {
    service=$1
    expected_port=$2
    if grep -q "EXPOSE $expected_port" "$service/Dockerfile" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $service - Port $expected_port"
    else
        echo -e "${RED}✗${NC} $service - Incorrect port in Dockerfile"
        ((ERRORS++))
    fi
}

check_port "artemis" "8000"
check_port "home-manager" "8020"
check_port "vehicle-manager" "8030"
check_port "meal-planner" "8010"
echo ""

echo "============================================================"
echo "  PRE-FLIGHT CHECK SUMMARY"
echo "============================================================"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready for deployment.${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS warnings. Review before deploying.${NC}"
    exit 0
else
    echo -e "${RED}✗ $ERRORS errors found. Fix issues before deploying.${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠ $WARNINGS warnings.${NC}"
    fi
    exit 1
fi
