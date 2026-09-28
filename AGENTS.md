do not make changes to RTL_examples/ 
do not make any commits or pushes, but you can freely read other branches and history from git

Evaluate generated designs with continuous measurements, not performance pass/fail
thresholds or aggregate scores. Preserve precision differences (14 bits is better
than 13), clock cycles, fabric usage, and timing separately. First establish the
intended computation and low cycle counts, then improve precision/resources;
timing closure is normally the last optimization step. Tool exit codes indicate
whether a valid measurement could be obtained, not whether performance is good.

There is no such thing as "passing". putting any performance metric through a threshold decreases everyone's ability to understand how good something is. 14 bits of preciison beats 13 bits. the difference matters. 

At the beginning what matters is getting it right (like >4 bits or so of precision) and low number of clock cycles. Meeting timing is usually the last step in optimization. 
