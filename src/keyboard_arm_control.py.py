import pyfirmata
import time
import threading
import sys
import msvcrt  # Built-in library for key presses on Windows

# --- CONFIGURATION ---
PORT = 'COM7' 

# Define the digital pins on the Arduino
SERVO_PINS = {
    'base_1': 10,       # PWM
    'base_2': 9,        # PWM
    'shoulder': 11,     # PWM
    'elbow': 6,         # PWM
    'arm_bend': 5,      # PWM
    'gripper_rotate': 3,  # PWM
    'gripper_grasp': 4,   # NOT PWM on Uno - may be jerky
}

# Define the neutral (starting) angles for each servo (0-180 degrees)
NEUTRAL_ANGLES = {
    'base_1': 180,
    'base_2': 0,
    'shoulder': 180,
    'elbow': 100,
    'arm_bend': 75,
    'gripper_rotate': 90,
    'gripper_grasp': 80,   # Start with the gripper open
}

# --- CONTROL CONSTANTS ---
INCREMENT = 5           # Degrees to move servo with each key press
PLAYBACK_DELAY = 0.02   # Seconds between steps during playback
RETURN_SPEED_DELAY = 0.02 # Seconds between steps during return-to-home

# --- GLOBAL VARIABLES ---
board = None
servos = {}
current_angles = NEUTRAL_ANGLES.copy()
is_recording = False
recorded_path = []
stop_event = threading.Event() # For signaling threads to stop cleanly

# --- CORE FUNCTIONS ---

def setup_board():
    """Establishes connection, configures servos, and moves to neutral position."""
    global board, servos
    print(f"Attempting to connect to Arduino on port {PORT}...")
    try:
        board = pyfirmata.Arduino(PORT)
        time.sleep(2) # Allow time for the connection to establish
        print("Connection successful!")

        # Configure all servo pins
        for name, pin in SERVO_PINS.items():
            servos[name] = board.get_pin(f'd:{pin}:s')
            print(f"  - Configured servo '{name}' on pin {pin}.")
        
        print("\nMoving servos to neutral positions...")
        # Move all servos to their neutral positions one by one
        for name, angle in NEUTRAL_ANGLES.items():
            servos[name].write(angle)
            time.sleep(0.15) # A small delay between servo initializations

        print("Initial homing complete. Arm is in neutral position.")
        print_instructions()
        return True
    except Exception as e:
        print(f"ERROR: Could not connect to Arduino on {PORT}.")
        print("Please check the port and make sure StandardFirmataPlus is uploaded.")
        print(f"Error details: {e}")
        return False

def move_servo(name, angle):
    """Moves a specified servo to a given angle, respecting limits (0-180)."""
    # Clamp the angle to the valid range of 0-180 degrees
    angle = max(0, min(180, angle))
    if name in servos:
        current_angles[name] = angle
        servos[name].write(angle)
    else:
        print(f"\nWARNING: Servo '{name}' not found.")

def record_current_state():
    """If recording is active, appends the current state of all servos to the path."""
    if is_recording:
        recorded_path.append(current_angles.copy())
        # NOTE: We removed the print statement from here to prevent console spam.
        # The 'print_status' function will show the point count.

def return_to_neutral_slowly():
    """Slowly moves all servos back to their defined neutral positions."""
    if is_recording:
        print("\nCannot return to home while recording.")
        return

    print("\nReturning to neutral position slowly...")
    temp_angles = current_angles.copy()

    # Continue until all servos have reached their neutral angle
    while any(int(temp_angles[name]) != NEUTRAL_ANGLES[name] for name in SERVO_PINS):
        if stop_event.is_set(): # Check for exit signal
            print("Return to neutral interrupted.")
            break

        for name in SERVO_PINS.keys():
            current = temp_angles[name]
            neutral = NEUTRAL_ANGLES[name]

            if int(current) != neutral:
                # Move one step closer to the neutral angle
                if current < neutral:
                    new_angle = current + 1
                else:
                    new_angle = current - 1
                move_servo(name, new_angle)
                temp_angles[name] = new_angle
        
        time.sleep(RETURN_SPEED_DELAY)
    
    if not stop_event.is_set():
        print("Arm has returned to neutral position.")
    print_status() # Update the status line

def playback_path():
    """Plays back the recorded path of servo movements one time."""
    if not recorded_path:
        print("\nNothing recorded to play back.")
        return

    print("\n--- Starting Playback ---")
    for i, angles_state in enumerate(recorded_path):
        if stop_event.is_set(): # Check for exit signal
            print("Playback interrupted.")
            break

        for name, angle in angles_state.items():
            servos[name].write(angle)
            current_angles[name] = angle
        time.sleep(PLAYBACK_DELAY)

    print("--- Playback Finished ---")
    print_status() # Update the status line

def print_instructions():
    """Prints the control instructions to the console."""
    print("\n--- Robotic Arm Controls ---")
    print("Press a key to control the arm. (No 'Enter' needed)")
    print("\n--- Movement ---")
    print(f"Base:           <Left Arrow> / <Right Arrow> (Moves by {INCREMENT}°)")
    print(f"Shoulder:       <Up Arrow> / <Down Arrow>   (Moves by {INCREMENT}°)")
    print(f"Elbow:          'w' / 's'                   (Moves by {INCREMENT}°)")
    print(f"Arm Bend:       't' / 'y'                   (Moves by {INCREMENT}°)")
    print(f"Gripper Rotate: 'a' / 'd'                   (Moves by {INCREMENT}°)")
    print(f"Gripper Grasp:  '1' (Close) / '2' (Open)  (Moves by {INCREMENT}°)")
    print("\n--- System ---")
    print("Start Record:   'r'")
    print("Stop Record:    'o'")
    print("Playback Path:  'p'")
    print("Return to Home: 'h'")
    print("Show Help:      '?' (Question Mark)")
    print("Exit Program:   <Esc> (Escape Key)")
    print("----------------------------")

def print_status():
    """Prints the current servo angles and recording status on one line."""
    # Format all angles to 3 characters to prevent line "jiggling"
    b1 = f"{current_angles['base_1']:3}"
    b2 = f"{current_angles['base_2']:3}"
    sh = f"{current_angles['shoulder']:3}"
    el = f"{current_angles['elbow']:3}"
    ab = f"{current_angles['arm_bend']:3}"
    gr = f"{current_angles['gripper_rotate']:3}"
    gg = f"{current_angles['gripper_grasp']:3}"

    angle_str = (
        f"Base: {b1}/{b2} | Shoulder: {sh} | Elbow: {el} | "
        f"Arm Bend: {ab} | Rotate: {gr} | Grasp: {gg}"
    )
    
    rec_str = ""
    if is_recording:
        rec_str = f" | REC: ON | Points: {len(recorded_path)}"
    
    # Write the status line, using \r to return to the start of the line
    # Pad with spaces to overwrite any previous, longer text
    status_line = f"\r{angle_str}{rec_str}"
    sys.stdout.write(status_line + " " * (79 - len(status_line)))
    sys.stdout.flush()

def process_command(command):
    """Parses and executes the user's command."""
    global is_recording
    
    # --- Movement Controls ---
    if command == 'left':
        move_servo('base_1', current_angles['base_1'] + INCREMENT)
        move_servo('base_2', current_angles['base_2'] - INCREMENT)
    elif command == 'right':
        move_servo('base_1', current_angles['base_1'] - INCREMENT)
        move_servo('base_2', current_angles['base_2'] + INCREMENT)
        
    elif command == 'down':
        move_servo('shoulder', current_angles['shoulder'] + INCREMENT)
    elif command == 'up':
        move_servo('shoulder', current_angles['shoulder'] - INCREMENT)

    elif command == 'w':
        move_servo('elbow', current_angles['elbow'] + INCREMENT)
    elif command == 's':
        move_servo('elbow', current_angles['elbow'] - INCREMENT)
        
    elif command == 't':
        move_servo('arm_bend', current_angles['arm_bend'] + INCREMENT)
    elif command == 'y':
        move_servo('arm_bend', current_angles['arm_bend'] - INCREMENT)
        
    elif command == 'a':
        move_servo('gripper_rotate', current_angles['gripper_rotate'] + INCREMENT)
    elif command == 'd':
        move_servo('gripper_rotate', current_angles['gripper_rotate'] - INCREMENT)

    elif command == '1':
        move_servo('gripper_grasp', current_angles['gripper_grasp'] + INCREMENT) # Close
    elif command == '2':
        move_servo('gripper_grasp', current_angles['gripper_grasp'] - INCREMENT) # Open
    
    # --- System Controls ---
    elif command == 'r':
        if not is_recording:
            is_recording = True
            recorded_path.clear()
            print("\nREC: Recording started. Press 'o' to stop.")
        else:
            print("\nAlready recording.")
    
    elif command == 'p':
        if is_recording:
            print("\nStop recording ('o') before playing back.")
        else:
            # Run playback in a thread so it doesn't block key presses
            playback_thread = threading.Thread(target=playback_path, daemon=True)
            playback_thread.start()
    
    elif command == 'o':
        if is_recording:
            is_recording = False
            print(f"\nREC: Recording stopped. {len(recorded_path)} points saved.")
        else:
            print("\nNot currently recording.")

    elif command == 'h':
        # Run 'home' in a thread so it doesn't block key presses
        home_thread = threading.Thread(target=return_to_neutral_slowly, daemon=True)
        home_thread.start()
    
    elif command == 'help':
        print_instructions()

    else:
        # Don't do anything for unmapped keys
        return # Don't record an unknown command

    # If the command was a movement command, record the state
    if command not in ['r', 'p', 'o', 'h', 'help']:
        record_current_state()

# --- MAIN EXECUTION ---

def main_loop():
    """Main loop to listen for single-key presses using msvcrt."""
    print_status() # Show the initial status
    while not stop_event.is_set():
        try:
            # Check if a key has been pressed
            if msvcrt.kbhit():
                key = msvcrt.getch()

                # --- Handle Special Keys (Arrows, Esc) ---
                if key == b'\xe0': # Special key prefix
                    try:
                        key2 = msvcrt.getch() # Read the second part
                        if key2 == b'H':
                            process_command('up')
                        elif key2 == b'P':
                            process_command('down')
                        elif key2 == b'K':
                            process_command('left')
                        elif key2 == b'M':
                            process_command('right')
                    except:
                        pass # Ignore errors in special key reading
                    
                # --- Escape key (b'\x1b') ---
                elif key == b'\x1b':
                    print("\n'Esc' key pressed. Shutting down...")
                    stop_event.set()
                    break
                
                # --- Handle Normal Keys (Letters/Numbers) ---
                else:
                    try:
                        char = key.decode('utf-8')
                        if char == '?':
                            process_command('help')
                        elif char in ['w', 's', 't', 'y', 'a', 'd', '1', '2', 'r', 'o', 'p', 'h']:
                            process_command(char)
                    except UnicodeDecodeError:
                        pass # Ignore keys we can't decode

                # Update the status line after every command
                print_status()

            # Prevent the loop from using 100% CPU
            time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nProgram interrupted (Ctrl+C). Shutting down.")
            stop_event.set()
            break

if __name__ == "__main__":
    if setup_board():
        try:
            main_loop() # Call the new main loop
        finally:
            stop_event.set() # Signal all threads to stop
            print("\nExiting Arduino connection.")
            if board:
                board.exit()
            print("Shutdown complete.")