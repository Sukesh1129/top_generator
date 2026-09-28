import pandas as pd
import argparse
import sys
import os

def generate_connected_top(excel_file, top_module_name, output_file):
    try:
        xls = pd.ExcelFile(excel_file)
    except FileNotFoundError:
        print(f"Error: The file {excel_file} was not found.")
        sys.exit(1)

    global_nets = {} # Internal wires: { "net_name": "[31:0]" }
    top_ports = {}   # External ports: { "net_name": {"width": "[31:0]", "dir": "input"} }
    modules_data = [] 
    
    # NEW: Track drivers to detect conflicts
    net_drivers = {} # { "net_name": ["uart_tx.tx_ready", "dma_ctrl.uart_wvalid"] }

    # --- Pass 1: Extract all connections, top ports, and widths ---
    for sheet_name in xls.sheet_names:
        if sheet_name == 'Empty': continue

        df = pd.read_excel(xls, sheet_name=sheet_name)
        
        # Normalize column headers
        col_map = {str(c).strip().lower(): c for c in df.columns}
        conn_col = col_map.get('connection') or col_map.get('net') or col_map.get('connect')
        top_col  = col_map.get('top_port') or col_map.get('top') or col_map.get('is_top')

        mod_name = sheet_name
        inst_name = f"I_{mod_name.upper()}"
        
        ports = []
        params = []

        for _, row in df.iterrows():
            cat = str(row.get('Category', '')).strip()
            name = str(row.get('Name', '')).strip()
            if name == 'nan' or not name: continue

            if cat == 'Port':
                direction = str(row.get('Direction', '')).strip().lower()
                width = str(row.get('Width', '')).strip()
                
                # Clean up width
                width_str = ""
                if width and width not in ['-', '1-bit', 'nan']:
                    width_str = width if width.startswith('[') else f"[{width}]"

                # Determine Net Name
                net_name = f"{mod_name}_{name}"
                if conn_col and pd.notna(row[conn_col]):
                    val = str(row[conn_col]).strip()
                    if val and val != 'nan':
                        net_name = val

                # Track Output Drivers for Conflict Detection
                if direction in ['output', 'out', 'inout']:
                    if net_name not in net_drivers:
                        net_drivers[net_name] = []
                    net_drivers[net_name].append(f"{mod_name}.{name}")

                # Check if this should be a Top-Level Port
                is_top = False
                if top_col and pd.notna(row[top_col]):
                    val = str(row[top_col]).strip().lower()
                    if val in ['yes', 'y', 'true', '1', 'top']:
                        is_top = True

                # Register the net or top port
                if is_top:
                    if net_name not in top_ports:
                        top_ports[net_name] = {'width': width_str, 'dir': direction}
                else:
                    if net_name not in global_nets:
                        global_nets[net_name] = width_str

                ports.append({'name': name, 'net': net_name, 'dir': direction})

            elif cat == 'Parameter':
                val = str(row.get('Value', '')).strip()
                val_str = val if val not in ['nan', '-'] else "0"
                params.append({'name': name, 'val': val_str})

        modules_data.append({
            'mod_name': mod_name,
            'inst_name': inst_name,
            'ports': ports,
            'params': params
        })

    # --- NEW: Multi-Driver Conflict Check ---
    conflict_found = False
    print("--- Running Sanity Checks ---")
    for net, drivers in net_drivers.items():
        if len(drivers) > 1:
            print(f"[WARNING] Multi-driver conflict on net '{net}'!")
            print(f"          Driven by: {', '.join(drivers)}")
            conflict_found = True
            
    if conflict_found:
        print("[WARNING] Verilog will still be generated, but please fix the Excel sheet to prevent 'X' states.\n")
    else:
        print("[PASS] No multi-driver conflicts detected.\n")


    # --- Pass 2: Generate Verilog ---
    with open(output_file, 'w') as f:
        f.write(f"// Auto-generated Top-Level Wrapper from Excel\n")
        f.write(f"module {top_module_name} (\n")
        
        # 1. Generate Top-Level Ports
        top_port_list = list(top_ports.keys())
        for i, port in enumerate(sorted(top_port_list)):
            comma = "," if i < len(top_port_list) - 1 else ""
            p_dir = top_ports[port]['dir']
            p_wid = top_ports[port]['width']
            f.write(f"    {p_dir:<6} wire {p_wid:<10} {port}{comma}\n")
            
        f.write(");\n\n")
        
        # 2. Generate Internal Wires
        f.write("    // =========================================\n")
        f.write("    // Internal Global Nets\n")
        f.write("    // =========================================\n")
        
        for net in sorted(global_nets.keys()):
            width = global_nets[net]
            f.write(f"    wire {width:<10} {net};\n")
        
        f.write("\n    // =========================================\n")
        f.write("    // Module Instantiations\n")
        f.write("    // =========================================\n\n")
        
        # 3. Generate Instantiations
        for mod in modules_data:
            f.write(f"    {mod['mod_name']} ")
            
            # Parameters
            if mod['params']:
                f.write("\n    #(\n")
                for i, p in enumerate(mod['params']):
                    comma = "," if i < len(mod['params']) - 1 else ""
                    f.write(f"        .{p['name']:<15} ( {p['val']:<15} ){comma}\n")
                f.write("    ) ")
                
            f.write(f"{mod['inst_name']} (\n")
            
            # Ports
            for i, p in enumerate(mod['ports']):
                comma = "," if i < len(mod['ports']) - 1 else " "
                dir_comment = f"// {p['dir'].upper()[0]:<2} :" if p['dir'] else ""
                f.write(f"        .{p['name']:<15} ( {p['net']:<15} ){comma} {dir_comment}\n")
                
            f.write(f"    );  // {mod['inst_name']}\n\n")

    print(f"Success! Top-level module generated at: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a Connected Top-Level Verilog module.")
    parser.add_argument("-i", "--input", required=True, help="Input Excel file (.xlsx)")
    parser.add_argument("-t", "--top_name", default="chip_top", help="Name of the top-level module")
    parser.add_argument("-o", "--output", default="chip_top.sv", help="Output System Verilog file (.sv)")
    
    args = parser.parse_args()
    generate_connected_top(args.input, args.top_name, args.output)