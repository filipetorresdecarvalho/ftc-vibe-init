import os
import json
import subprocess
import requests
import sys
import re
from pathlib import Path

# --- CONFIGURATION ---
OLLAMA_MODEL = "llama3"  # Change to your preferred model (e.g., mistral, llama3:70b)
OLLAMA_API = "http://localhost:11434/api/chat"
DOCUMENTS_BASE = Path.home() / "Documents" / "VibeCode"

# --- COMPLEX PROMPTS ---

INTERVIEWER_SYSTEM_PROMPT = """
You are an expert Technical Product Manager and Software Architect. 
Your goal is to interview the user to gather requirements for a new coding project.

INSTRUCTIONS:
1. Start by introducing yourself and asking the user about the core idea.
2. Ask ONE question at a time. Wait for the user's response.
3. You MUST dig deep into specific technical requirements. Ask about:
   - Primary Language (Python, TypeScript, Go, Rust, etc.)
   - Framework preferences (FastAPI, Next.js, React Native, Electron, etc.)
   - Target Platform (Web, Mobile, Desktop, CLI, SaaS)
   - Data Storage (Postgres, Mongo, SQLite, Local files)
   - External APIs or Integrations (OpenAI, Zhipu, Stripe, etc.)
   - Complexity Level (Simple script, Full-stack app, Microservice)
4. Once you have gathered sufficient detail, tell the user you are ready to generate the plan.
5. When asked to 'Generate Configuration', output ONLY a valid JSON object with the following schema and NO OTHER TEXT:

JSON SCHEMA:
{
  "project_slug": "hyphenated-project-name-with-3-random-words-and-numbers",
  "project_title": "Human Readable Title",
  "language": "python | node | go | rust | other",
  "framework": "fastapi | nextjs | react | none",
  "platform": "web | mobile | desktop | cli",
  "description": "A detailed project description.",
  "tech_stack": ["list", "of", "technologies"],
  "environment_variables": ["LIST_OF_ENV_KEYS_NEEDED"],
  "notes": "Any special setup notes."
}
"""

DOC_GENERATOR_PROMPT = """
You are a technical writer. Based on the following JSON configuration, generate raw content for three files.
Return ONLY a JSON object with keys: 'readme_content', 'tasks_content', 'skills_content'.

CONFIG:
{config_json}
"""

# --- HELPER FUNCTIONS ---

def query_ollama(messages, stream=True):
    """Sends a chat history to Ollama and returns the response."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream
    }
    
    try:
        response = requests.post(OLLAMA_API, json=payload, stream=stream)
        response.raise_for_status()
        
        if stream:
            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']
                        print(content, end='', flush=True)
                        full_response += content
            print() # Newline after streaming
            return full_response
        else:
            return response.json()['message']['content']
            
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to Ollama. Is it running? (Run 'ollama serve')")
        sys.exit(1)

def extract_json(text):
    """Extracts JSON string from a text block."""
    try:
        # Try to find JSON block enclosed in braces
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except json.JSONDecodeError:
        return None

def run_cmd(command, cwd=None):
    """Runs a shell command."""
    subprocess.run(command, shell=True, check=True, cwd=cwd)

# --- MAIN WORKFLOW ---

def main():
    print("🧠 Vibe Coding Initializer (Powered by Local Ollama)")
    print("------------------------------------------------------")
    
    # 1. Interview Phase
    print(f"🤖 Connecting to local model: {OLLAMA_MODEL}...")
    conversation_history = [{"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT}]
    
    # Initial prompt to get the ball rolling
    print("\nAI: ", end="")
    initial_greeting = query_ollama(conversation_history + [{"role": "user", "content": "Start the interview."}])
    conversation_history.append({"role": "assistant", "content": initial_greeting})
    
    while True:
        user_input = input("You: ")
        conversation_history.append({"role": "user", "content": user_input})
        
        print("AI: ", end="")
        response = query_ollama(conversation_history)
        conversation_history.append({"role": "assistant", "content": response})
        
        # Check if user wants to generate config or if AI signaled ready
        if "generate configuration" in user_input.lower() or "generate configuration" in response.lower() or "generate the plan" in response.lower():
            break

    # 2. Generate Configuration JSON
    print("\n⏳ Generating final project configuration...")
    # Force JSON output
    json_prompt = "Based on our conversation, output the final JSON configuration now. Remember, ONLY output the JSON object."
    conversation_history.append({"role": "user", "content": json_prompt})
    
    # Non-stream for JSON to ensure clean parsing
    raw_json_response = query_ollama(conversation_history, stream=False)
    config = extract_json(raw_json_response)
    
    if not config:
        print("❌ Failed to parse valid JSON from Ollama. Response was:")
        print(raw_json_response)
        sys.exit(1)
        
    project_slug = config.get('project_slug', 'new-vibe-project')
    project_title = config.get('project_title', 'New Project')
    language = config.get('language', 'python').lower()
    
    print(f"✅ Project Configured: {project_title}")
    print(f"   Slug: {project_slug}")

    # 3. Create File Structure
    project_path = DOCUMENTS_BASE / project_slug
    project_path.mkdir(parents=True, exist_ok=True)
    print(f"📂 Folder created: {project_path}")

    # 4. Generate Documentation Content via Ollama
    print("📝 Generating Documentation, Tasks, and Skills matrix...")
    doc_gen_payload = [
        {"role": "system", "content": DOC_GENERATOR_PROMPT.format(config_json=json.dumps(config, indent=2))},
        {"role": "user", "content": "Generate the three files content now. Return only JSON with keys readme_content, tasks_content, skills_content."}
    ]
    
    doc_raw = query_ollama(doc_gen_payload, stream=False)
    docs = extract_json(doc_raw)
    
    if docs:
        (project_path / "README.md").write_text(docs.get('readme_content', '# Project'))
        (project_path / "tasks.md").write_text(docs.get('tasks_content', '## Tasks'))
        (project_path / "skills.md").write_text(docs.get('skills_content', '## Skills'))
    else:
        print("⚠️ AI failed to generate docs format, creating templates.")
        (project_path / "README.md").write_text(f"# {project_title}")
        (project_path / "tasks.md").write_text("## Todo")
        (project_path / "skills.md").write_text("## Stack")

    # 5. Create Dynamic Dockerfile
    dockerfile_content = generate_dockerfile(config, project_path)
    (project_path / "Dockerfile").write_text(dockerfile_content)
    
    # Create .gitignore
    (project_path / ".gitignore").write_text("node_modules\n__pycache__\n.env\n.venv\n*.pyc\n.DS_Store")

    # 6. Git & GitHub Setup
    print("🐙 Setting up Git Repository...")
    try:
        run_cmd("git init", cwd=project_path)
        run_cmd("git add .", cwd=project_path)
        run_cmd('git commit -m "Initial commit from Vibe Coder"', cwd=project_path)
        
        # Create private repo
        repo_url = subprocess.check_output(
            f'gh repo create {project_slug} --private --description "{config.get("description", "")}" --source=. --remote=origin --push',
            shell=True, cwd=project_path
        ).decode('utf-8').strip()
        print(f"✅ GitHub Repo: {repo_url}")
    except subprocess.CalledProcessError as e:
        print("⚠️ Git/GitHub setup failed. Maybe repo exists or gh not logged in.")

    # 7. Docker Build & Run
    print("🐳 Building Docker Container...")
    env_vars = " -e ".join([f"{key}=''" for key in config.get('environment_variables', [])]) # Placeholder vars
    
    try:
        run_cmd(f"docker build -t {project_slug} .", cwd=project_path)
        
        # Check if container exists
        try:
            subprocess.run(f"docker rm -f {project_slug}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

        run_cmd(f"docker run -d --name {project_slug} -v \"{project_path}:/app\" {project_slug}")
        
        print("\n------------------------------------------------------")
        print(f"🚀 SUCCESS! Project {project_title} is ready.")
        print(f"   Folder: {project_path}")
        print(f"   Container: {project_slug}")
        print(f"   To enter: docker exec -it {project_slug} /bin/bash")
        print("------------------------------------------------------")
        
    except subprocess.CalledProcessError:
        print("❌ Docker build failed.")

def generate_dockerfile(config, path):
    lang = config.get('language', 'python').lower()
    
    if lang in ['python', 'py']:
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git curl build-essential
RUN pip install zhipuai ollama
COPY . .
CMD ["tail", "-f", "/dev/null"]
"""
    elif lang in ['node', 'typescript', 'javascript', 'ts', 'js']:
        return f"""FROM node:20-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git curl
RUN npm install -g pnpm
COPY . .
CMD ["tail", "-f", "/dev/null"]
"""
    elif lang in ['go', 'golang']:
        return f"""FROM golang:1.22-alpine
WORKDIR /app
RUN apk add --no-cache git curl
COPY . .
CMD ["tail", "-f", "/dev/null"]
"""
    else:
        return f"""FROM ubuntu:22.04
WORKDIR /app
RUN apt-get update && apt-get install -y git curl build-essential
CMD ["tail", "-f", "/dev/null"]
"""

if __name__ == "__main__":
    main()
