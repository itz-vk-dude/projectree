import csv
import random

# CONFIGURATION
TOTAL_PROJECTS = 30000
FILENAME = "my_projects.csv"

# EXPANDED DATA POOLS FOR UNIQUE TITLES
interests = ['Web', 'AI', 'IoT', 'Security',
             'Data', 'Mobile', 'Blockchain', 'Cloud']
ecosystems = ['Software', 'Hardware']
levels = ['Beginner', 'Intermediate', 'Advanced']
languages = ['Python', 'JavaScript', 'C++', 'Java', 'Rust', 'Go', 'Swift']

prefixes = [
    "Scalable",
    "Enterprise",
    "Autonomous",
    "High-Performance",
    "Distributed",
    "Secure",
    "Next-Gen",
    "Cloud-Native",
    "Decentralized",
    "Integrated",
    "Smart",
    "Proactive",
    "Reactive",
    "Modular",
    "Universal",
    "Adaptive",
    "Robust",
    "Global"]
contexts = [
    "Finance",
    "Healthcare",
    "E-commerce",
    "Logistics",
    "Social",
    "Cybersecurity",
    "Agriculture",
    "Education",
    "Energy",
    "Retail",
    "Space",
    "Legal",
    "Automotive",
    "Media",
    "Telecom"]
types = {
    'Web': [
        "Dashboard",
        "Portal",
        "Micro-frontend",
        "API Gateway",
        "CMS",
        "Service Layer",
        "Stack",
        "Hub"],
    'AI': [
        "Neural Net",
        "Predictor",
        "Classifier",
        "Optimizer",
        "Inference Engine",
        "Bot",
        "Modeler"],
    'IoT': [
        "Gateway",
        "Sensor Node",
        "Controller",
        "Tracker",
        "Embedded Hub",
        "Telemetry Unit"],
    'Security': [
        "Vault",
        "Scanner",
        "Protocol",
        "Shield",
        "Auditor",
        "Firewall",
        "Auth Engine"],
    'Blockchain': [
        "Ledger",
        "Wallet",
        "Node",
        "Contract Hub",
        "Validator",
        "DeFi Bridge"],
    'Data': [
        "Pipeline",
        "Visualizer",
        "Scraper",
        "Processor",
        "Warehouse",
        "Miner",
        "Lake Engine"],
    'Mobile': [
        "Application",
        "Utility",
        "Sync Hub",
        "Interface",
        "Native Tool",
        "Mobile Wallet"],
    'Cloud': [
        "Orchestrator",
        "Service",
        "Balancer",
        "Container",
        "Lambda Suite",
        "Cloud Logic"]}

# KNOWLEDGE BASE FOR STEPS (Keep as is)
step_templates = {
    'Software': [
        "Architecture Design[:]Define the project roadmap and data flow between components.",
        "Environment Setup[:]Initialize your workspace and install the necessary dependencies and frameworks.",
        "Logic Development[:]Code the core business logic and handle data processing requirements.",
        "Database Integration[:]Connect the application to a structured database and establish relationships.",
        "Security Hardening[:]Implement authentication layers and perform input sanitization.",
        "Final Deployment[:]Package the application and host it on a scalable production server."
    ],
    'Hardware': [
        "Schematic Mapping[:]Draft the electrical circuit and identify all required GPIO pinouts.",
        "Component Sourcing[:]Acquire the necessary sensors, microcontrollers, and actuators.",
        "Firmware Coding[:]Develop the low-level instructions to control hardware behavior.",
        "Circuit Prototyping[:]Assemble the hardware components on a breadboard and test signal stability.",
        "Cloud Connectivity[:]Configure the communication module to send data to a remote dashboard.",
        "Enclosure Design[:]Create a protective housing to ensure hardware durability."
    ]
}


def generate_project(i):
    interest = random.choice(interests)
    lang = random.choice(languages)
    level = random.choice(levels)
    p_type = 'Hardware' if interest == 'IoT' else random.choice(ecosystems)

    # --- REMOVED THE "v{i}" HERE ---
    # We use 3 random words to create a unique professional name
    title = f"{random.choice(prefixes)} {random.choice(contexts)} {random.choice(types[interest])}"

    desc = f"A {level} {interest} project built with {lang}. This system focuses on {p_type} architecture and performance optimization."
    output = f"A fully functional {interest} solution with optimized {lang} code."
    days = 5 if level == 'Beginner' else 12 if level == 'Intermediate' else 21

    raw_steps = random.sample(step_templates[p_type], 5)
    steps = "|".join(raw_steps)

    return [title, desc, interest, p_type, level, lang, output, days, steps]


print(
    f"[*] Generating {TOTAL_PROJECTS} unique projects without version tags...")

with open(FILENAME, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['title', 'description', 'interest', 'type', 'level',
                    'language', 'expected_output', 'duration_days', 'steps'])
    for i in range(1, TOTAL_PROJECTS + 1):
        writer.writerow(generate_project(i))

print(f"[OK] Success! {FILENAME} is clean and professional.")
