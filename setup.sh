#!/bin/bash

set -e

echo "========================================="
echo "Minecraft AI Agent Setup"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.11+ required, found $python_version"
    exit 1
fi
echo "✓ Python $python_version"

# Check Java version
echo "Checking Java version..."
if command -v java &> /dev/null; then
    java_version=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d. -f1)
    if [ "$java_version" -ge 17 ]; then
        echo "✓ Java $java_version"
    else
        echo "⚠ Java 17+ recommended for Minecraft mod, found version $java_version"
    fi
else
    echo "⚠ Java not found. Install Java 17+ to build the Minecraft mod"
fi

# Check Docker
echo "Checking Docker..."
if command -v docker &> /dev/null; then
    echo "✓ Docker installed"
else
    echo "⚠ Docker not found. Install Docker to run the vLLM server"
fi

echo ""
echo "Installing Python agent..."
cd agent
pip install -e .
echo "✓ Python agent installed"

echo ""
echo "Creating .env file from example..."
cd ..
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file (edit as needed)"
else
    echo "⚠ .env file already exists"
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the vLLM server:"
echo "   cd docker && docker-compose up -d"
echo ""
echo "2. Build the Minecraft mod:"
echo "   cd minecraft-mod && ./gradlew build"
echo "   Copy build/libs/*.jar to your Minecraft mods folder"
echo ""
echo "3. Start Minecraft with Fabric and the mod"
echo ""
echo "4. Run the agent:"
echo "   mcagent run --goal 'explore and gather wood'"
echo ""
echo "For more information, see README.md"
