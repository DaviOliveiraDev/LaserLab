import re
import math
from typing import Dict, Any, List, Tuple

class OMAParser:
    """
    Parser for Vision Council / OMA (Optical Manufacturers Association) standard lens description files.
    """
    
    @staticmethod
    def parse_file(file_content: str) -> Dict[str, Any]:
        """
        Parses raw OMA file content and returns a dictionary of key-value pairs,
        converting special tags like TRCFMT into structured lists of 2D coordinates.
        """
        parsed_tags = {}
        raw_lines = file_content.splitlines()
        
        # Buffer to accumulate tags that may be split across multiple lines (like TRCFMT)
        multi_line_buffers = {}
        
        for line in raw_lines:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#") or line.startswith(";"):
                continue
                
            # OMA commands are structured as KEY=VALUE
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip().upper()
                val = val.strip()
                
                # If key already exists, append or merge (common in OMA for sequential data)
                if key in parsed_tags:
                    if isinstance(parsed_tags[key], list):
                        parsed_tags[key].append(val)
                    else:
                        parsed_tags[key] = [parsed_tags[key], val]
                else:
                    parsed_tags[key] = val
            else:
                # If line doesn't have an '=', it might be a continuation of the previous tag
                # E.g. some systems dump raw trace points without the 'TRCFMT=' prefix on subsequent lines
                pass

        # Post-process multi-line tags that should be combined
        # Let's search for tags that might contain arrays (like TRCFMT, RADIUS, etc.)
        for key in list(parsed_tags.keys()):
            val = parsed_tags[key]
            if isinstance(val, list):
                # If it's a list, join them together
                # Usually TRCFMT split lines can be concatenated with a semicolon or comma
                parsed_tags[key] = ";".join(val)

        # Convert to standardized numeric types
        result = {}
        for key, val in parsed_tags.items():
            result[key] = OMAParser._convert_value(key, val)
            
        # Parse the shape from TRCFMT if present
        if "TRCFMT" in result:
            result["shape_coordinates"] = OMAParser._extract_shape_coordinates(result["TRCFMT"])
            
        return result

    @staticmethod
    def _convert_value(key: str, val: str) -> Any:
        """Helper to convert string values to numeric types when applicable."""
        # Clean up formatting characters (like quotes)
        val = val.strip('"\'')
        
        # Tags that are usually integers
        int_tags = {"JOB", "AXIS", "PBASE"}
        # Tags that are usually floats
        float_tags = {"LDG", "ADD", "PRISM", "OBL", "PRP", "MRP", "DRP", "NRP", "DBL", "FPD"}
        
        if key in int_tags:
            try:
                return int(val)
            except ValueError:
                pass
        elif key in float_tags:
            try:
                return float(val)
            except ValueError:
                pass
        
        # Try generic conversions
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            return val

    @staticmethod
    def _extract_shape_coordinates(trcfmt_data: str) -> List[Tuple[float, float]]:
        """
        Parses OMA TRCFMT (Trace Format) data and extracts 2D Cartesian coordinates in millimeters.
        
        Standard TRCFMT format is:
        TRCFMT = side ; no_of_points ; radial_step ; axial_step ; radial_type ; r1 ; r2 ; ... ; rn
        
        Units:
        - OMA standard radius values are in hundredths of a millimeter (0.01 mm).
        - We divide by 100.0 to convert to physical millimeters.
        """
        if not trcfmt_data:
            return []
            
        # Split tokens. Tokens can be separated by semicolons (standard) or commas
        tokens = [t.strip() for t in re.split(r'[;,]', trcfmt_data) if t.strip()]
        
        if len(tokens) < 6:
            return []
            
        try:
            side = tokens[0]
            no_of_points = int(tokens[1])
            radial_step = float(tokens[2])  # Step in degrees (e.g., 1.0 or 0.5)
            axial_step = float(tokens[3])
            radial_type = tokens[4].upper() # 'R' is standard radial polar
            
            radius_tokens = tokens[5:]
            
            # If the parser merged lines, there could be extra elements. Let's limit to no_of_points
            radius_values = []
            for r in radius_tokens[:no_of_points]:
                try:
                    # OMA standard: Radius values are in 0.01 mm (hundredths of a millimeter)
                    radius_values.append(float(r) / 100.0)
                except ValueError:
                    continue
            
            # If we don't have enough values, pad or interpolate
            if len(radius_values) < no_of_points:
                # Return whatever coordinates we can parse safely
                no_of_points = len(radius_values)
                
            coordinates = []
            for i, radius in enumerate(radius_values):
                # Calculate angle in radians. Usually starts at 0 degrees.
                angle_deg = i * radial_step
                angle_rad = math.radians(angle_deg)
                
                # Polar to Cartesian conversion
                x = radius * math.cos(angle_rad)
                y = radius * math.sin(angle_rad)
                coordinates.append((x, y))
                
            return coordinates
            
        except Exception as e:
            # Silently return empty or log error if formatting is incorrect
            print(f"Error parsing TRCFMT: {e}")
            return []
