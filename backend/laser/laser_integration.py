import math
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re
from typing import Dict, Any, List, Tuple, Callable
import logging

logger = logging.getLogger(__name__)

# Basic vector stroke definitions for numerals (0-9) and some letters to write "ADD" and brand codes in G-code
# Represented as coordinate lists relative to a bottom-left (0,0) of a 1.0 x 1.5 grid
STROKE_FONT: Dict[str, List[List[Tuple[float, float]]]] = {
    "0": [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.5), (0.0, 1.5), (0.0, 0.0)], [(0.0, 0.0), (1.0, 1.5)]],
    "1": [[(0.5, 0.0), (0.5, 1.5), (0.2, 1.2)]],
    "2": [[(0.0, 1.5), (1.0, 1.5), (1.0, 0.75), (0.0, 0.0), (1.0, 0.0)]],
    "3": [[(0.0, 1.5), (1.0, 1.5), (1.0, 0.0), (0.0, 0.0)], [(0.0, 0.75), (1.0, 0.75)]],
    "4": [[(0.0, 1.5), (0.0, 0.75), (1.0, 0.75)], [(1.0, 1.5), (1.0, 0.0)]],
    "5": [[(1.0, 1.5), (0.0, 1.5), (0.0, 0.75), (1.0, 0.75), (1.0, 0.0), (0.0, 0.0)]],
    "6": [[(1.0, 1.5), (0.0, 1.5), (0.0, 0.0), (1.0, 0.0), (1.0, 0.75), (0.0, 0.75)]],
    "7": [[(0.0, 1.5), (1.0, 1.5), (0.3, 0.0)]],
    "8": [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.5), (0.0, 1.5), (0.0, 0.0)], [(0.0, 0.75), (1.0, 0.75)]],
    "9": [[(1.0, 0.0), (1.0, 1.5), (0.0, 1.5), (0.0, 0.75), (1.0, 0.75)]],
    "+": [[(0.2, 0.75), (0.8, 0.75)], [(0.5, 0.45), (0.5, 1.05)]],
    "A": [[(0.0, 0.0), (0.5, 1.5), (1.0, 0.0)], [(0.2, 0.6), (0.8, 0.6)]],
    "D": [[(0.0, 0.0), (0.0, 1.5), (0.7, 1.5), (1.0, 1.1), (1.0, 0.4), (0.7, 0.0), (0.0, 0.0)]],
    "F": [[(0.0, 0.0), (0.0, 1.5), (1.0, 1.5)], [(0.0, 0.75), (0.7, 0.75)]],
    "S": [[(1.0, 1.3), (0.2, 1.5), (0.0, 1.0), (1.0, 0.5), (0.8, 0.0), (0.0, 0.2)]],
    "V": [[(0.0, 1.5), (0.5, 0.0), (1.0, 1.5)]]
}

class LaserPathGenerator:
    """
    Translates lens and marking metadata into industrial laser file formats
    (SVG, G-code, native LightBurn LBRN2 XML) and manages GRBL serial communication.
    """
    
    @staticmethod
    def generate_svg(geo_results: Dict[str, Any]) -> str:
        """
        Creates an organized, color-coded SVG vector representation of the lens.
        Includes dedicated CSS classes for tool layers (lens border, safe zone) and engraving layers.
        Upgraded to a high-fidelity Industrial CAD Schematic overlay with 5mm grid,
        yellow dashed fitting cross, vector translation arrows, and a CRT status readout.
        """
        # Outer bounds
        bbox = geo_results["bbox"]
        width = math.ceil(bbox["width"] + 20)
        height = math.ceil(bbox["height"] + 20)
        
        # Center SVG coordinate space about geometric center
        cx = width / 2.0
        cy = height / 2.0
        
        # Convert physical lens center (which is typical 0,0 in coordinates) to SVG pixel center
        # Flip Y axis because screen space is positive down, physical is positive up
        def to_svg(x: float, y: float) -> Tuple[float, float]:
            return cx + x, cy - y

        lens_outline = geo_results["lens_outline"]
        safety_outline = geo_results["safety_outline"]
        m = geo_results["markings"]["physical"]
        params = geo_results["parameters"]
        
        ref_pt_type = geo_results["markings"].get("reference_point_type", "PRP")
        fc_dist = geo_results["markings"].get("fitting_cross_dist", 4.0)
        
        # Build SVG Document string
        svg = []
        svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">')
        svg.append('  <!-- Design styles -->')
        svg.append('  <style>')
        svg.append('    .lens-border { fill: rgba(15, 23, 42, 0.6); stroke: #38bdf8; stroke-width: 0.8; }')
        svg.append('    .safety-margin { fill: none; stroke: #f43f5e; stroke-width: 0.5; stroke-dasharray: 3, 3; }')
        svg.append('    .grid-line { stroke: #334155; stroke-width: 0.15; }')
        svg.append('    .grid-line-major { stroke: #475569; stroke-width: 0.3; }')
        svg.append('    .alignment-axis { stroke: rgba(14, 165, 233, 0.4); stroke-width: 0.5; stroke-dasharray: 2, 2; }')
        svg.append('    .laser-marking { fill: none; stroke: #22c55e; stroke-width: 0.6; }')
        svg.append('    .laser-text { fill: #22c55e; font-family: "Courier New", monospace; font-weight: bold; font-size: 2.8px; text-anchor: middle; }')
        svg.append('    .vector-arrow { stroke: #0ea5e9; stroke-width: 0.4; stroke-dasharray: 1, 1; }')
        svg.append('    .fitting-cross { stroke: #eab308; stroke-width: 0.6; stroke-dasharray: 2, 1; }')
        svg.append('    .fitting-cross-center { fill: none; stroke: #eab308; stroke-width: 0.4; }')
        svg.append('    .crt-text { fill: #38bdf8; font-family: "Courier New", monospace; font-size: 2px; font-weight: bold; }')
        svg.append('    .crt-title { fill: #eab308; font-family: "Courier New", monospace; font-size: 2.2px; font-weight: bold; }')
        svg.append('  </style>')
        
        # Arrow Marker Definition
        svg.append('  <defs>')
        svg.append('    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">')
        svg.append('      <path d="M 0 0 L 10 5 L 0 10 z" fill="#0ea5e9" />')
        svg.append('    </marker>')
        svg.append('  </defs>')
        
        # Background Grid (Dark Slate Industrial Theme)
        svg.append(f'  <rect width="{width}" height="{height}" fill="#090d16" rx="8" stroke="#1e293b" stroke-width="1.5" />')
        
        # Draw 5mm Spaced Fine Coordinate Grid Lines
        half_w = width / 2.0
        half_h = height / 2.0
        
        # Draw grid lines (-45 to 45 mm range covering physical lens diameters)
        for i in range(-50, 51, 5):
            if i == 0:
                continue
            # Grid Class (Major thicker on multiples of 10)
            grid_class = "grid-line-major" if i % 10 == 0 else "grid-line"
            
            # Horizontal lines
            hx1, hy1 = to_svg(-half_w, i)
            hx2, hy2 = to_svg(half_w, i)
            svg.append(f'  <line x1="{hx1}" y1="{hy1}" x2="{hx2}" y2="{hy2}" class="{grid_class}" />')
            
            # Vertical lines
            vx1, vy1 = to_svg(i, -half_h)
            vx2, vy2 = to_svg(i, half_h)
            svg.append(f'  <line x1="{vx1}" y1="{vy1}" x2="{vx2}" y2="{vy2}" class="{grid_class}" />')
            
        # Draw primary alignment axis lines (0,0)
        ax1, ay1 = to_svg(-half_w, 0)
        ax2, ay2 = to_svg(half_w, 0)
        svg.append(f'  <line x1="{ax1}" y1="{ay1}" x2="{ax2}" y2="{ay2}" class="alignment-axis" />')
        
        ayx1, ayy1 = to_svg(0, -half_h)
        ayx2, ayy2 = to_svg(0, half_h)
        svg.append(f'  <line x1="{ayx1}" y1="{ayy1}" x2="{ayx2}" y2="{ayy2}" class="alignment-axis" />')
        
        # 1. Lens Outline Polygon
        if lens_outline:
            points_str = " ".join([f"{to_svg(p['x'], p['y'])[0]},{to_svg(p['x'], p['y'])[1]}" for p in lens_outline])
            svg.append(f'  <polygon points="{points_str}" class="lens-border" />')
            
        # 2. Safety Contour
        if safety_outline:
            points_str = " ".join([f"{to_svg(p['x'], p['y'])[0]},{to_svg(p['x'], p['y'])[1]}" for p in safety_outline])
            svg.append(f'  <polygon points="{points_str}" class="safety-margin" />')
            
        # 3. Blocking Center / Geometric Origin
        svg.append(f'  <circle cx="{cx}" cy="{cy}" r="1.0" fill="#f8fafc" />')
        svg.append(f'  <circle cx="{cx}" cy="{cy}" r="2.5" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="0.3" />')

        # 4. Reference Point representation (e.g. PRP, DRP)
        if "reference_point" in m:
            rx, ry = to_svg(m["reference_point"]["x"], m["reference_point"]["y"])
            svg.append(f'  <!-- Reference Point ({ref_pt_type}) -->')
            svg.append(f'  <circle cx="{rx}" cy="{ry}" r="0.6" fill="#0ea5e9" />')
            # Text tag
            svg.append(f'  <text x="{rx + 2.0}" y="{ry + 0.7}" fill="#0ea5e9" font-family="Courier New" font-size="2px" font-weight="bold">{ref_pt_type}</text>')

        # 5. Fitting Cross representation (Yellow dashed crosshair)
        if "fitting_cross" in m:
            fcx, fcy = to_svg(m["fitting_cross"]["x"], m["fitting_cross"]["y"])
            svg.append('  <!-- Fitting Cross -->')
            # Horizontal crosshair line
            svg.append(f'  <line x1="{fcx - 4.5}" y1="{fcy}" x2="{fcx + 4.5}" y2="{fcy}" class="fitting-cross" />')
            # Vertical crosshair line
            svg.append(f'  <line x1="{fcx}" y1="{fcy - 4.5}" x2="{fcx}" y2="{fcy + 4.5}" class="fitting-cross" />')
            # Center target circle
            svg.append(f'  <circle cx="{fcx}" cy="{fcy}" r="0.75" class="fitting-cross-center" />')
            svg.append(f'  <text x="{fcx + 2.0}" y="{fcy - 1.2}" fill="#eab308" font-family="Courier New" font-size="2px" font-weight="bold">FC</text>')

        # 6. Nasal and Temporal Markings (Physical green technical alignment coordinates)
        # Nasal Technical Circle + Cross
        nx, ny = to_svg(m["nasal"]["x"], m["nasal"]["y"])
        nasal_color = "#22c55e" if m["nasal"]["in_bounds"] else "#f43f5e"
        svg.append(f'  <!-- Nasal Mark -->')
        svg.append(f'  <circle cx="{nx}" cy="{ny}" r="0.5" fill="none" stroke="{nasal_color}" stroke-width="0.4" />')
        svg.append(f'  <line x1="{nx-1.2}" y1="{ny}" x2="{nx+1.2}" y2="{ny}" stroke="{nasal_color}" stroke-width="0.3" />')
        svg.append(f'  <line x1="{nx}" y1="{ny-1.2}" x2="{nx}" y2="{ny+1.2}" stroke="{nasal_color}" stroke-width="0.3" />')
        
        # Temporal Technical Circle + Cross
        tx, ty = to_svg(m["temporal"]["x"], m["temporal"]["y"])
        temporal_color = "#22c55e" if m["temporal"]["in_bounds"] else "#f43f5e"
        svg.append(f'  <!-- Temporal Mark -->')
        svg.append(f'  <circle cx="{tx}" cy="{ty}" r="0.5" fill="none" stroke="{temporal_color}" stroke-width="0.4" />')
        svg.append(f'  <line x1="{tx-1.2}" y1="{ty}" x2="{tx+1.2}" y2="{ty}" stroke="{temporal_color}" stroke-width="0.3" />')
        svg.append(f'  <line x1="{tx}" y1="{ty-1.2}" x2="{tx}" y2="{ty+1.2}" stroke="{temporal_color}" stroke-width="0.3" />')
        
        # 7. Translation Vector Arrows from Reference Point to Markings
        if "reference_point" in m:
            rx, ry = to_svg(m["reference_point"]["x"], m["reference_point"]["y"])
            svg.append('  <!-- Translation Vectors -->')
            # Vector to Nasal
            svg.append(f'  <line x1="{rx}" y1="{ry}" x2="{nx}" y2="{ny}" class="vector-arrow" marker-end="url(#arrow)" />')
            # Vector to Temporal
            svg.append(f'  <line x1="{rx}" y1="{ry}" x2="{tx}" y2="{ty}" class="vector-arrow" marker-end="url(#arrow)" />')

        # 8. Brand Logo & Addition text engraving simulations
        bx, by = to_svg(m["brand_text"]["x"], m["brand_text"]["y"])
        ax, ay = to_svg(m["addition_text"]["x"], m["addition_text"]["y"])
        
        # Shift slightly downwards for proper visual baseline alignment
        svg.append(f'  <text x="{bx}" y="{by + 0.8}" class="laser-text">{geo_results["markings"]["addition_text"]}</text>')
        svg.append(f'  <text x="{ax}" y="{ay + 0.8}" class="laser-text">FF</text>')
        
        # 9. CRT System Status Terminal Overlay (Box in top-left corner)
        svg.append('  <!-- CNC Terminal readout overlay -->')
        overlay_x = 4.0
        overlay_y = 4.0
        svg.append(f'  <rect x="{overlay_x}" y="{overlay_y}" width="28" height="20" fill="rgba(9, 13, 22, 0.85)" stroke="#38bdf8" stroke-width="0.4" rx="1.5" />')
        svg.append(f'  <line x1="{overlay_x}" y1="{overlay_y + 3.2}" x2="{overlay_x + 28}" y2="{overlay_y + 3.2}" stroke="#38bdf8" stroke-width="0.25" />')
        svg.append(f'  <text x="{overlay_x + 14}" y="{overlay_y + 2.3}" class="crt-title" text-anchor="middle">LASERLAB SYSTEM v1.0</text>')
        
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 6}" class="crt-text">TEMPLATE: {geo_results["markings"].get("job_id", "DEFAULT")}</text>')
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 8.5}" class="crt-text">REF PT:   {ref_pt_type} ({m["reference_point"]["x"]:.1f}, {m["reference_point"]["y"]:.1f})</text>')
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 11}" class="crt-text">FC DIST:  +{fc_dist:.1f} mm</text>')
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 13.5}" class="crt-text">OFFSET X: {params.get("template_offset_x", 0.0):+.2f} mm</text>')
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 16}" class="crt-text">OFFSET Y: {params.get("template_offset_y", 0.0):+.2f} mm</text>')
        svg.append(f'  <text x="{overlay_x + 2}" y="{overlay_y + 18.5}" class="crt-text">ROTATION: {params.get("template_rotation", 0.0):+.2f}°</text>')
        
        svg.append('</svg>')
        return "\n".join(svg)

    @staticmethod
    def generate_gcode(
        geo_results: Dict[str, Any],
        speed: int = 1500,
        power: int = 200
    ) -> str:
        """
        Generates production-ready GRBL G-code for engraving progressive markings.
        Marks standard 1mm alignment circles and generates clean stroke lines for ADD / Brand markings.
        """
        # Laser targets are from the base-curve sagitta corrected, fully calibrated list
        m = geo_results["markings"]["calibrated_laser"]
        
        gcode = []
        # Header setup
        gcode.append("; --- Ophthalmic Lens Laser Engraving MVP G-Code ---")
        gcode.append(f"; Job ID: {geo_results['markings'].get('job_id', 'UNKNOWN')}")
        gcode.append(f"; Eye: {geo_results['markings']['eye']}")
        gcode.append("G21 ; Units: Millimeters")
        gcode.append("G90 ; Coordinate: Absolute Positioning")
        gcode.append("M5  ; Laser Off")
        gcode.append("S0  ; Power: 0")
        
        def write_circle(cx: float, cy: float, radius: float = 0.5, segments: int = 16):
            """Appends coordinates to trace a smooth polygon approximating a circle."""
            coords = []
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)
                coords.append((x, y))
                
            # Rapid to start
            gcode.append(f"G0 X{coords[0][0]:.3f} Y{coords[0][1]:.3f}")
            # Laser on
            gcode.append(f"M3 S{power} ; Engrave circle")
            # Trace circle
            for x, y in coords[1:]:
                gcode.append(f"G1 X{x:.3f} Y{y:.3f} F{speed}")
            # Laser off
            gcode.append("M5")

        def write_stroke_text(text: str, cx: float, cy: float, size: float = 1.8):
            """Renders text characters using the built-in stroke font dictionary."""
            char_spacing = size * 1.1
            total_w = len(text) * char_spacing
            
            # Start position (centered horizontally)
            start_x = cx - total_w / 2.0
            
            for ch_idx, char in enumerate(text.upper()):
                if char not in STROKE_FONT:
                    continue
                
                ch_x = start_x + ch_idx * char_spacing
                ch_y = cy
                
                # Fetch character strokes
                paths = STROKE_FONT[char]
                for path in paths:
                    # Move to starting point of stroke
                    px, py = path[0]
                    gx = ch_x + px * size
                    gy = ch_y + py * size
                    gcode.append(f"G0 X{gx:.3f} Y{gy:.3f}")
                    # Laser On
                    gcode.append(f"M3 S{power}")
                    
                    # Draw remaining stroke line segments
                    for px, py in path[1:]:
                        gx = ch_x + px * size
                        gy = ch_y + py * size
                        gcode.append(f"G1 X{gx:.3f} Y{gy:.3f} F{speed}")
                    # Laser Off
                    gcode.append("M5")

        # 1. Nasal Alignment Circle
        write_circle(m["nasal"]["x"], m["nasal"]["y"], radius=0.5)
        # Nasal Addition value text
        write_stroke_text(geo_results["markings"]["addition_text"], m["brand_text"]["x"], m["brand_text"]["y"])
        
        # 2. Temporal Alignment Circle
        write_circle(m["temporal"]["x"], m["temporal"]["y"], radius=0.5)
        # Temporal brand identifier ("FF" for Freeform)
        write_stroke_text("FF", m["addition_text"]["x"], m["addition_text"]["y"])

        # Footer
        gcode.append("G0 X0 Y0 F3000 ; Return to home")
        gcode.append("M5 ; Safety laser off")
        gcode.append("; --- End of G-Code ---")
        
        return "\n".join(gcode)

    @staticmethod
    def generate_lbrn2(geo_results: Dict[str, Any]) -> str:
        """
        Generates a native LightBurn (.lbrn2) XML project file.
        Structures vectors on layers:
        - Layer 0 (Cyan): Engravings, output enabled.
        - Layer 1 (Red/Tool): Lens outlines, output disabled (used only for visual alignment).
        """
        # Fully calibrated marking positions
        m = geo_results["markings"]["calibrated_laser"]
        outline = geo_results["lens_outline"]
        
        root = ET.Element("LightBurnProject", AppVersion="1.4.01", FormatVersion="0", DBScale="1")
        ET.SubElement(root, "VariableText")
        
        # Custom cuts settings
        cut_setting = ET.SubElement(root, "CutSetting")
        
        # Engraving layer (index 0)
        ET.SubElement(
            cut_setting, "CutSetting",
            index="0", Name="Engrave Marks",
            Speed="1500", MaxPower="25", MinPower="10",
            Mode="Line", Output="1", Play="1", Priority="0"
        )
        
        # Lens shape border layer (index 1) - tool layer (Output="0")
        ET.SubElement(
            cut_setting, "CutSetting",
            index="1", Name="Lens Boundary (Tool)",
            Speed="2000", MaxPower="0", MinPower="0",
            Mode="Line", Output="0", Play="0", Priority="1"
        )
        
        # Outer group containing all geometry
        group = ET.SubElement(root, "Shape", Type="Group")
        
        # 1. Nasal technical circle (diameter 1mm -> Rx=Ry=0.5)
        ET.SubElement(
            group, "Shape", Type="Ellipse", CutIndex="0",
            Cx=f"{m['nasal']['x']:.4f}", Cy=f"{m['nasal']['y']:.4f}",
            Rx="0.5", Ry="0.5"
        )
        
        # 2. Temporal technical circle (diameter 1mm)
        ET.SubElement(
            group, "Shape", Type="Ellipse", CutIndex="0",
            Cx=f"{m['temporal']['x']:.4f}", Cy=f"{m['temporal']['y']:.4f}",
            Rx="0.5", Ry="0.5"
        )
        
        # 3. OMA lens border outline representation (Layer index 1)
        if outline:
            # Join outline points as a serialized line vector sequence in LightBurn format
            # LightBurn standard Path format contains point listings
            points_str = " ".join([f"{p['x']:.3f},{p['y']:.3f}" for p in outline])
            # Close the path back to the starting point
            points_str += f" {outline[0]['x']:.3f},{outline[0]['y']:.3f}"
            
            ET.SubElement(
                group, "Shape", Type="Path", CutIndex="1",
                Data=f"M {points_str} Z"
            )
            
        # Reformat XML string for human readability
        xml_str = ET.tostring(root, encoding="utf-8")
        parsed_xml = minidom.parseString(xml_str)
        return parsed_xml.toprettyxml(indent="  ")


class GRBLSerialStreamer:
    """
    Handles streaming of calculated G-code instructions directly to a connected 
    GRBL hardware controller over a serial COM port. Supports live simulation.
    """
    def __init__(self, port: str = "COM_MOCK", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.running = False
        
    def stream_gcode(
        self,
        gcode_text: str,
        progress_callback: Callable[[float], None] = None,
        line_callback: Callable[[int, str], bool] = None
    ) -> bool:
        """
        Streams G-code lines over serial using GRBL protocol (wait-for-ok).
        If port is "COM_MOCK", simulates transmission accurately for testing.
        """
        self.running = True
        lines = [line.strip() for line in gcode_text.splitlines() if line.strip() and not line.startswith(";")]
        total_lines = len(lines)
        
        if total_lines == 0:
            return True
            
        logger.info(f"Starting G-Code stream to laser (port: {self.port}). Total instructions: {total_lines}")
        
        if self.port == "COM_MOCK":
            # Simulate streaming
            for idx, line in enumerate(lines):
                if not self.running:
                    logger.warning("Streaming aborted by operator.")
                    return False
                
                if line_callback:
                    if not line_callback(idx, line):
                        logger.warning("Streaming halted by line callback (alarm/abort).")
                        return False
                    
                time.sleep(0.08)  # Simulate 80ms laser execution/transmission time for high-fidelity animations
                progress = (idx + 1) / total_lines * 100.0
                if progress_callback:
                    progress_callback(progress)
                    
            logger.info("Laser marking completed successfully (MOCK).")
            return True
            
        # Physical serial transmission
        import serial
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1.0)
            # Wake up GRBL
            ser.write(b"\r\n\r\n")
            time.sleep(2.0)  # Wait for GRBL to initialize
            ser.flushInput()
            
            for idx, line in enumerate(lines):
                if not self.running:
                    logger.warning("Streaming aborted by operator.")
                    ser.close()
                    return False
                
                if line_callback:
                    if not line_callback(idx, line):
                        logger.warning("Streaming halted by line callback (alarm/abort).")
                        ser.close()
                        return False
                
                # Write command line
                cmd = f"{line}\n".encode("utf-8")
                ser.write(cmd)
                
                # Wait for GRBL response 'ok'
                response = ser.readline().decode("utf-8").strip()
                while not response or "ok" not in response.lower():
                    if "error" in response.lower():
                        logger.error(f"GRBL hardware returned error: {response} for line: {line}")
                        ser.close()
                        return False
                    response = ser.readline().decode("utf-8").strip()
                    
                progress = (idx + 1) / total_lines * 100.0
                if progress_callback:
                    progress_callback(progress)
                    
            ser.close()
            logger.info("Laser marking streaming completed successfully over COM.")
            return True
            
        except Exception as e:
            logger.error(f"Failed communicating with laser over {self.port}: {e}")
            return False
            
    def stop(self):
        """Cancels any ongoing G-code serial stream immediately."""
        self.running = False
