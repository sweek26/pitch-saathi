# Motivation Nudges

Short, warm encouragements shown automatically after a strong turn, roughly
every few turns — never after every turn, never on a weak/short one. Picked
by plain code (`demo/server.py`), not the model — see the "code controls
timing" decision for this feature. Edit the wording freely; each `- ` line
is one nudge, and code picks randomly from all of them (avoiding an
immediate repeat).

- 🌸 बहुत अच्छा दीदी, ऐसे ही बात करती रहिए!
- 👏 बहुत बढ़िया दीदी! आपने बात को बहुत अच्छे से समझाया।
- 😊 शाबाश दीदी! आपका समझाने का तरीक़ा बहुत अच्छा है।
- 💪 बहुत अच्छा जा रहा है दीदी, बस ऐसे ही आत्मविश्वास के साथ बात करती रहिए!
- 🌱 बिलकुल सही दीदी! आप धीरे-धीरे बहुत अच्छा अभ्यास कर रही हैं।
- ❤️ बहुत बढ़िया! घर वाले की बात ध्यान से सुनकर जवाब देना बहुत अच्छी आदत है।
- 👏 वाह दीदी! आपने उनकी परेशानी को समझकर जवाब दिया।
- 🌼 ऐसे ही दीदी, प्यार से और धैर्य से समझाती रहिए।
