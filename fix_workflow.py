
import json
import uuid

# Load original
with open('Evolution_Video_Cloud_Complete.json', 'r') as f:
    workflow = json.load(f)

nodes = workflow['nodes']
connections = workflow['connections']

# Helper to generate unique ID
def get_id():
    return str(uuid.uuid4())

# Find the "Store Video URLs" node to hook onto
store_node = next(n for n in nodes if n['name'] == 'Store Video URLs')
start_x = store_node['position'][0]
start_y = store_node['position'][1]

# We will remove the old synchronous nodes
nodes_to_remove = ['Concat Videos via FFmpeg API', 'Merge Audio via FFmpeg API', 'Add Subtitles via FFmpeg API']
workflow['nodes'] = [n for n in nodes if n['name'] not in nodes_to_remove]
# Remove their connections
for name in list(connections.keys()):
    if name in nodes_to_remove:
        del connections[name]
    # Remove connections TO them (cleaned up during rebuilding)

# Function to create an async block
def create_async_block(name_prefix, api_url, json_body, start_x, start_y, input_node_name, result_field_path="data.result.url"):
    """
    Creates [Start] -> [Wait] -> [Poll] -> [If] -> (Done)
    Returns: list of nodes, final_node_name, next_x_pos
    """
    start_id = get_id()
    wait_id = get_id()
    poll_id = get_id()
    if_id = get_id()
    
    start_node_name = f"{name_prefix} Start"
    wait_node_name = f"{name_prefix} Wait"
    poll_node_name = f"{name_prefix} Poll"
    if_node_name = f"{name_prefix} Check"
    
    # Node 1: Start Job
    node_start = {
        "parameters": {
            "method": "POST",
            "url": api_url,
            "sendHeaders": True,
            "headerParameters": { "parameters": [
                { "name": "Content-Type", "value": "application/json" },
                { "name": "X-API-Key", "value": "ffmpeg_sk_9a7b3c2e1f4d8a6b5c3e7f2a1b9d4c8e" }
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json_body
        },
        "id": start_id,
        "name": start_node_name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [start_x + 200, start_y]
    }
    
    # Node 2: Wait
    node_wait = {
        "parameters": { "amount": 10, "unit": "seconds" },
        "id": wait_id,
        "name": wait_node_name,
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1,
        "position": [start_x + 400, start_y]
    }
    
    # Node 3: Poll
    node_poll = {
        "parameters": {
            "method": "GET",
            "url": f"=https://arrogant-debby-rudraksh-034175cd.koyeb.app/tasks/{{{{ $('{start_node_name}').item.json.job_id }}}}",
            "sendHeaders": True,
            "headerParameters": { "parameters": [
                { "name": "X-API-Key", "value": "ffmpeg_sk_9a7b3c2e1f4d8a6b5c3e7f2a1b9d4c8e" }
            ]}
        },
        "id": poll_id,
        "name": poll_node_name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [start_x + 600, start_y]
    }
    
    # Node 4: If Completed
    # Check if status == 'completed'
    node_if = {
        "parameters": {
            "conditions": {
                "options": { "caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 3 },
                "conditions": [{
                    "id": get_id(),
                    "leftValue": "={{ $json.status }}",
                    "rightValue": "completed",
                    "operator": { "type": "string", "operation": "equals" }
                }]
            }
        },
        "id": if_id,
        "name": if_node_name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [start_x + 800, start_y]
    }
    
    new_nodes = [node_start, node_wait, node_poll, node_if]
    
    # Connections
    # Input -> Start
    if input_node_name not in connections: connections[input_node_name] = {"main": [[],[],[],[]]} # Assuming index 0
    # Append to main[0]
    if not connections[input_node_name].get("main"): connections[input_node_name]["main"] = [[]]
    connections[input_node_name]["main"][0].append({ "node": start_node_name, "type": "main", "index": 0 })
    
    # Start -> Wait
    connections[start_node_name] = { "main": [[{ "node": wait_node_name, "type": "main", "index": 0 }]] }
    
    # Wait -> Poll
    connections[wait_node_name] = { "main": [[{ "node": poll_node_name, "type": "main", "index": 0 }]] }
    
    # Poll -> If
    connections[poll_node_name] = { "main": [[{ "node": if_node_name, "type": "main", "index": 0 }]] }
    
    # If False -> Wait (Loop)
    conns_if = { "main": [[], []] } # [True, False]
    conns_if["main"][1].append({ "node": wait_node_name, "type": "main", "index": 0 })
    connections[if_node_name] = conns_if
    
    # Success branch (main[0]) is the output of the block
    # But wait, the downstream node needs the RESULT URL.
    # The 'If' node passes the JSON from 'Poll'.
    # Poll returns { status: completed, result: { url: ... } }
    # So the next node will receive this.
    
    return new_nodes, if_node_name, start_x + 800

# BUILD THE CHAIN

# 1. Concat
concat_body = "={{ JSON.stringify({video_urls: $('Store Video URLs').all().map(x => x.json.videoUrl), trim_duration: 5}) }}"
concat_nodes, concat_out, current_x = create_async_block(
    "Concat", 
    "https://arrogant-debby-rudraksh-034175cd.koyeb.app/concat", 
    concat_body, 
    start_x, start_y, 
    "Store Video URLs"
)
workflow['nodes'].extend(concat_nodes)

# 2. Generate On Screen Text
# Needs to run after Concat to be in sequence, OR parallel.
# Let's put it in sequence to keep it simple, but we must pass 'url' through.
# The original 'Generate On Screen Text' node is at index ?
gen_text_node = next(n for n in workflow['nodes'] if n['name'] == 'Generate On Screen Text ') # Note space
# Fix its code to pass through 'url'
# It uses: return [{ content: assContent }];
# Change to: return [{ json: { content: assContent, url: $('Concat Poll').item.json.result.url } }];
# Wait, access the item from the PREVIOUS node (which is If -> Poll).
# Use $input.item.json.result.url
new_code = gen_text_node['parameters']['jsCode'].replace(
    "return [{ content: assContent }];",
    "const inputUrl = $('Concat Poll').item.json.result.url;\nreturn [{ json: { content: assContent, url: inputUrl } }];"
)
gen_text_node['parameters']['jsCode'] = new_code
gen_text_node['position'] = [current_x + 200, start_y]

# Connect Concat Out (If True) -> Gen Text
connections[concat_out]["main"][0].append({ "node": gen_text_node['name'], "type": "main", "index": 0 })

current_x += 200 # For Gen Text

# 3. Merge Audio
# Input: url (from Gen Text), audio_url
merge_body = "={{ JSON.stringify({video_url: $json.url, audio_url: \"https://pub-879b72d29274423bab4fd53b5946501d.r2.dev/background_music.mp3\", shortest: true}) }}"
merge_nodes, merge_out, current_x = create_async_block(
    "Merge Audio", 
    "https://arrogant-debby-rudraksh-034175cd.koyeb.app/merge-audio", 
    merge_body, 
    current_x, start_y, 
    gen_text_node['name']
)
workflow['nodes'].extend(merge_nodes)

# 4. Add Subtitles
# Input: url (from Merge Audio), subtitle_content (from Gen Text)
# Note: Merge Audio Poll result will be { status: completed, result: { url: ... } }. So $json.result.url
# Wait, Create Async Block 'If' node passes the Poll output.
# Poll output structure: { "status": "completed", "result": { "url": "..." }, ... }
# So we need to access $json.result.url
sub_body = "={{ JSON.stringify({video_url: $json.result.url, subtitle_content: $('Generate On Screen Text ').first().json.content, format: \"ass\"}) }}"
# Note: accessed via node name for subtitle content, which is fine.

sub_nodes, sub_out, current_x = create_async_block(
    "Add Subtitles", 
    "https://arrogant-debby-rudraksh-034175cd.koyeb.app/add-subtitles", 
    sub_body, 
    current_x, start_y, 
    merge_out
)
workflow['nodes'].extend(sub_nodes)

# Save
with open('Evolution_Video_Cloud_Async.json', 'w') as f:
    json.dump(workflow, f, indent=2)

print("Generated Evolution_Video_Cloud_Async.json")
