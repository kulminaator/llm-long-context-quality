A little tool to generate chain of thought texts for LLM-s that they need to iterate through.

Each day in the log opens with a weather record (e.g. "It was a cold, windy overcast day.").
Some entries are fuzzy "standing instructions" ("...if sunlight was visible, the tank is to
receive N extra liters") whose effect depends on that day's weather — many of them are false
flags that never fire, so the model must track the weather per day as well as the volumes.

Usage:
Pick a folder like 16k, grab the water_tank_log.txt and questions.txt and feed them into the LLM tool of choice.
For example by using guide.txt as a template. The aim is to see if the llm can actually follow a thought and details far enough.

Once the LLM generates the answer, compare it to the answer_key.txt


We have pregenerated the water tank logs and answers with according context lengths into folders 16k, 32k, 64k, 128k
