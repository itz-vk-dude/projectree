import random

interests = ['Web', 'AI', 'IoT', 'Security',
             'Data', 'Mobile', 'Blockchain', 'Cloud']
ecosystems = ['Software', 'Hardware']
levels = ['Beginner', 'Intermediate', 'Advanced']
languages = ['Python', 'JavaScript', 'C++', 'Java', 'Rust', 'Go', 'Swift']

# THE KNOWLEDGE BASE: Detailed descriptions for every step in every field
step_knowledge = {
    'Web': [
        ("Architecture Design", "Define the Sitemap and Wireframes. Map out how data flows between the Frontend and the Backend API."),
        ("Environment Setup", "Install Node.js or Python. Initialize your package manager and install essential libraries like Express or Flask."),
        ("Database Integration", "Create the MySQL schema. Define tables for users, products, or logs, and establish primary key relationships."),
        ("Backend Logic", "Develop the RESTful API endpoints. Implement CRUD operations to handle data requests from the client."),
        ("Frontend UI", "Build the user interface using HTML/CSS or React. Ensure the design is responsive and user-friendly."),
        ("Security Hardening", "Implement JWT or OAuth for user login. Sanitize all inputs to prevent SQL injection and XSS attacks.")
    ],
    'AI': [
        ("Data Collection", "Gather the raw datasets required. Ensure you have enough samples for both training and validation phases."),
        ("Feature Engineering", "Clean the data. Remove null values, normalize numerical features, and encode categorical labels into numbers."),
        ("Model Selection", "Choose the right algorithm (like Random Forest or Neural Nets). Initialize the model using Scikit-Learn or TensorFlow."),
        ("Training Phase", "Fit the model to your training data. Monitor the loss and accuracy metrics to prevent overfitting."),
        ("Evaluation", "Test the model against the 'unseen' test data. Generate a confusion matrix to verify the precision of results."),
        ("Deployment", "Export the trained model and build a simple API to allow users to send data and receive real-time predictions.")
    ],
    'IoT': [
        ("Circuit Design", "Sketch the wiring diagram. Identify which GPIO pins on the microcontroller will connect to which sensors."),
        ("Prototyping", "Assemble the hardware on a breadboard. Connect sensors, actuators, and the power supply carefully."),
        ("Firmware Coding", "Write the C++ or Python code to read sensor data. Implement logic to handle hardware interrupts and loops."),
        ("Connectivity", "Configure the Wi-Fi or Bluetooth module. Establish a connection to an MQTT broker or a Cloud Dashboard."),
        ("Calibration", "Test the sensors in real-world conditions. Adjust the code thresholds to ensure accurate data readings."),
        ("Final Housing", "Design and 3D-print an enclosure. Secure the components to ensure the device is durable and portable.")
    ],
    'Security': [
        ("Vulnerability Assessment",
         "Scan the target system for open ports and outdated services. Map the potential attack surface."),
        ("Protocol Design", "Define the encryption standards (AES-256 or RSA). Sketch the handshake logic for secure communication."),
        ("Scripting Logic", "Write automated scripts to detect unusual patterns. Implement logging to track every unauthorized access attempt."),
        ("Hardening", "Disable unnecessary services. Configure firewalls and implement the principle of least privilege for users."),
        ("Reporting Engine", "Develop a dashboard that summarizes threats. Ensure it provides clear steps for incident response.")
    ]
}

# General steps for categories not listed above
general_steps = [
    ("Planning", "Analyze the requirements and create a project roadmap. Identify the core features and the target audience."),
    ("Development", "Write the primary codebase. Focus on modular, clean code that is easy to maintain and scale."),
    ("Testing", "Run unit tests and integration tests. Identify bugs and fix them before moving to the production phase."),
    ("Optimization", "Review the code for performance bottlenecks. Improve speed and reduce memory consumption where possible."),
    ("Documentation", "Write a detailed README file. Explain how to install, run, and contribute to the project.")
]


def generate_curriculum(interest):
    # Get specific steps for the category, or use general ones
    knowledge = step_knowledge.get(interest, general_steps)
    random.shuffle(knowledge)
    selected = knowledge[:5]  # Take 5 detailed steps

    # Format: Title[:]Detail|Title[:]Detail
    formatted_steps = []
    for title, detail in selected:
        formatted_steps.append(f"{title}[:]{detail}")

    return "|".join(formatted_steps)


with open('projects_setup.sql', 'w', encoding='utf-8') as f:
    f.write("DROP DATABASE IF EXISTS projectree_db;\nCREATE DATABASE projectree_db;\nUSE projectree_db;\n")
    f.write("CREATE TABLE projects (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(100), description TEXT, interest VARCHAR(50), type VARCHAR(50), level VARCHAR(50), language VARCHAR(50), status VARCHAR(20) DEFAULT 'Available', expected_output TEXT, duration_days INT, steps LONGTEXT);\n")

    used_titles = set()
    for i in range(10000):
        interest = random.choice(interests)
        title = f"{random.choice(['Secure', 'Advanced', 'Scalable', 'Smart'])} {interest} Engine v{i}"
        level = random.choice(levels)
        lang = random.choice(languages)
        p_type = 'Hardware' if interest == 'IoT' else random.choice(ecosystems)

        desc = f"This {level} project involves building a {title}. You will master {interest} concepts using {lang}."
        output = f"A professional {interest} system with a detailed technical report."
        days = 5 if level == 'Beginner' else 10

        # GENERATE THE DETAILED STEPS
        steps = generate_curriculum(interest)

        f.write(
            f"INSERT INTO projects (title, description, interest, type, level, language, expected_output, duration_days, steps) VALUES ('{title}', \"{desc}\", '{interest}', '{p_type}', '{level}', '{lang}', '{output}', {days}, '{steps}');\n")

print("10,000 Projects with DEEP DETAILS generated!")
