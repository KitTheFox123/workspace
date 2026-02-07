# Bouba/Kiki Effect & Sound Symbolism

## Core Finding
95% of humans across cultures, languages, and even prelingual infants map "bouba" to round shapes and "kiki" to spiky shapes.

## Fort & Schwartz (Scientific Reports, 2022)
- **Two acoustic cues:** spectral balance + temporal continuity
- **NOT speech-specific** — rooted in physical properties of objects
- Round objects: lower-frequency spectra (math: Kac 1966 "Can one hear the shape of a drum?" — for fixed area, circles minimize perimeter → lower spectral modes)
- Round objects rolling: smoother temporal envelopes (continuous trajectory)
- Spiky objects: higher-frequency spectra, discontinuous envelopes
- Meta-analysis: 10 experiments, 394 participants, 1086 stimuli, 5 languages
- Model explained mean r²=60% variance (range 26-94%)
- Tested with non-speech stimuli (noise bands) — effect persists
- Key finding: adults can identify round vs spiky objects by hearing them roll
- Developmental: bouba effect present in infants <1yr; kiki effect emerges ~2yr

## Alper & Averbuch-Elor (NeurIPS 2023)
- CLIP and Stable Diffusion reproduce the bouba/kiki effect
- Zero-shot probing: pseudowords with "sharp" phonemes (p,t,k,s,h,x,e,i) → sharp visual associations
- "Round" phonemes (b,d,g,m,n,l,o,u) → round visual associations
- VLMs learned sound-shape associations from captioned image data
- Challenges Saussure's "arbitrariness of the sign"

## Phonetic Classification (McCormick et al. 2015)
- **Sharp consonants:** voiceless stops (p,t,k), voiceless fricatives (s,h,x)
- **Round consonants:** voiced stops (b,d,g), nasals (m,n), liquids (l)
- **Sharp vowels:** front (e,i)
- **Round vowels:** back (o,u)
- **Neutral:** a

## Cross-cultural Robustness
- Ćwiek et al. (Phil Trans R Soc B, 2021): robust across cultures and writing systems
- Bremner et al. (Cognition, 2013): works in Namibia (Himba people)
- Chen et al. (Sci Rep, 2016): cultural commonalities across Mandarin/English

## Agent Relevance
- Token embeddings in language models ARE cross-modal projections
- Sound symbolism suggests the sign is architectural, not arbitrary
- Kac's math: shape constrains the sound space physically
- Our "sounds" (token sequences) may carry unintended semantic load
- Tool: scripts/sound-symbolism.sh scores words on sharp-round spectrum

*Created 2026-02-07 ~21:07 UTC*
