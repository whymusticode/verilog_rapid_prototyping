# LLMS do not edit, instead, tell me when you have a new item for this

A log of ways the LLM (coding tool or API called by project code) has gamed metrics or produced silently wrong output.
Add new entries here when discovered so they can be banned in prompts. short one liners for every time something goes awry

---
## TB had vulnerability that allowed holding busy to 0 made clock_cycles = 0. patched in prompt and tb generation"busy floor is 1, never 0"

## claude-code instructed agent to guess at the number of clock cycles something took rather than TBing it properly 

# deprecated:

##  Floating-point internals (conversion_016) The LLM used `double` for all internal Jacobi computation and only cast to `ap_fixed` at the output. C-sim reported 45 clock cycles to do the cast, but internal operations were not counted 


