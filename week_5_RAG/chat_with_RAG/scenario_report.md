# Chat-with-RAG — Long Scenario Test Report

Two ~13-message conversations driven automatically through a stateful `ChatAgent`.
Each turn: TaskState update → context-aware rewrite → retrieval + hard threshold + rerank → structured answer.

## Scenario: Cheshire Cat — shifting focus + mid-dialogue constraint

- **Q1 — loses the goal by message 12?** NO (goal retained ✅)
  - goals in TaskState at message 12: `['Learn everything about the Cheshire Cat', 'Summarize everything established about the Cheshire Cat']`
- **Q2 — keeps emitting Sources + Quotes?** YES ✅ (13/13 non-refusal answers had both blocks; 0 refusal(s))
- **Q3 (bonus) — mid-dialogue constraint held (Answer + Quotes)?** PARTIAL ⚠️ (6/7 post-rule turns clean; leaked at msg(s) [11] — the scene where the forbidden entity is a direct participant in the exact event asked about)

| # | User message | Rewritten query | Refusal? | Quotes | Sources | Goals in TaskState |
|---|---|---|---|---|---|---|
| 1 | I want to learn everything about the Cheshire Cat. To start: where in the story does Alice first meet him? | Where in Alice's Adventures in Wonderland does Alice first meet the Cheshire Cat? | no | yes | yes | Learn everything about the Cheshire Cat; Find where Alice first meets the Cheshire Cat |
| 2 | What is special or unusual about his grin? | What is special or unusual about the Cheshire Cat's grin? | no | yes | yes | Learn everything about the Cheshire Cat; Find where Alice first meets the Cheshire Cat; Understand what is special about the Cheshire Cat's grin |
| 3 | Does his grin stay behind even when the rest of him is gone? | Does the Cheshire Cat's grin stay behind even when the rest of him is gone? | no | yes | yes | Learn everything about the Cheshire Cat; Find where Alice first meets the Cheshire Cat; Understand what is special about the Cheshire Cat's grin; Clarify whether the grin remains after the cat disappears |
| 4 | Now let's switch focus to how he leaves: how exactly does the Cheshire Cat disappear? | How exactly does the Cheshire Cat disappear? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears |
| 5 | Does he vanish all at once, or slowly and part by part? | Does the Cheshire Cat vanish all at once, or slowly and part by part? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part |
| 6 | New rule for the rest of our chat: do NOT mention the Queen of Hearts at all. Keep the focus only on the Cat itself. | How exactly does the Cheshire Cat disappear? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part |
| 7 | When Alice asks him which way she ought to go, what does the Cat answer? | When Alice asks the Cheshire Cat which way she ought to go, what does the Cat answer? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part; Find out the Cat's answer to Alice's question about which way to go |
| 8 | What does the Cat say about everyone in that place being mad? | What does the Cheshire Cat say about everyone in Wonderland being mad? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part; Find out the Cat's answer to Alice's question about which way to go; Explain the Cat's statement about everyone in that place being mad |
| 9 | Remind me — which part of the Cat is the very last thing to fade away? | Which part of the Cheshire Cat is the very last thing to fade away? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part; Find out the Cat's answer to Alice's question about which way to go; Explain the Cat's statement about everyone in that place being mad; Remind which part of the Cat is the very last thing to fade away |
| 10 | Did the Cat show up again later, during the croquet game? | Did the Cheshire Cat appear again during the croquet game? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part; Find out the Cat's answer to Alice's question about which way to go; Explain the Cat's statement about everyone in that place being mad; Remind which part of the Cat is the very last thing to fade away; Check if the Cat reappears during the croquet game |
| 11 ⚠️LEAK | There was an argument about whether you can behead something that has no body — what was that about? | What was the argument about beheading something with no body in Alice's Adventures in Wonderland? | no | yes | yes | Learn everything about the Cheshire Cat; Understand how the Cheshire Cat disappears; Clarify the manner of his vanishing: all at once or part by part; Find out the Cat's answer to Alice's question about which way to go; Explain the Cat's statement about everyone in that place being mad; Remind which part of the Cat is the very last thing to fade away; Check if the Cat reappears during the croquet game; Explain the argument about beheading something with no body |
| 12 | Summarize everything we have established about the Cheshire Cat so far. | Summarize everything established about the Cheshire Cat in Alice's Adventures in Wonderland. | no | yes | yes | Learn everything about the Cheshire Cat; Summarize everything established about the Cheshire Cat |
| 13 | Last one: what is the Cat doing, and where, the first time Alice spots him in the kitchen scene? | What is the Cheshire Cat doing, and where, the first time Alice spots him in the kitchen scene? | no | yes | yes | Learn everything about the Cheshire Cat; Summarize everything established about the Cheshire Cat; Identify the Cat's location and action when Alice first spots him in the kitchen scene |

Final TaskState: `{'goals': ['Learn everything about the Cheshire Cat', 'Summarize everything established about the Cheshire Cat', "Identify the Cat's location and action when Alice first spots him in the kitchen scene"], 'constraints_and_terms': ['do not mention the Queen of Hearts'], 'user_clarifications': []}`

<details><summary>Answer bodies (for auditing the constraint check)</summary>

**msg 1** — The provided context does not contain any mention of the Cheshire Cat or Alice's first meeting with him. The fragments cover Chapters II and IV, which deal with the White Rabbit and the Pool of Tears, but not the Cheshire Cat.

**msg 2** — The Cheshire Cat's grin is special because it can remain visible after the rest of the cat has vanished. Alice observes that the grin "remained some time after the rest of it had gone," and she remarks that seeing "a grin without a cat" is "the most curious thing I ever saw in my life."

**msg 3** — Yes, the Cheshire Cat's grin remains visible even after the rest of the cat has vanished. The cat vanishes "quite slowly, beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone," and Alice thinks that seeing "a grin without a cat" is "the most curious thing I ever saw in my life."

**msg 4** — The Cheshire Cat disappears in two distinct ways. First, he vanishes suddenly and reappears at will, which makes Alice "quite giddy." Later, he vanishes "quite slowly, beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone." In a separate instance, when the executioner goes to fetch the Duchess, "the Cat's head began fading away" and "by the time he had come back with the Duchess, it had entirely disappeared."

**msg 5** — The Cheshire Cat does both. He first vanishes "suddenly" and reappears, which makes Alice "quite giddy." Later, he vanishes "quite slowly, beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone." So he can disappear both all at once and part by part.

**msg 6** — The Cheshire Cat vanishes in two distinct ways. He first disappears suddenly and reappears at will, which makes Alice "quite giddy." Later, he vanishes "quite slowly, beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone." In a separate instance, when the executioner goes to fetch the Duchess, "the Cat's head began fading away" and "by the time he had come back with the Duchess, it had entirely disappeared."

**msg 7** — The provided context does not contain the Cheshire Cat's answer to Alice's question about which way to go. The retrieved fragments discuss Dinah the cat, Alice falling down the rabbit-hole, and her conversation with the Caterpillar, but none include the Cheshire Cat's directions.

**msg 8** — The provided context does not contain the Cheshire Cat's statement about everyone in that place being mad. The retrieved fragments include the table of contents, the Mad Tea-Party chapter, and the Caucus-Race chapter, but none contain the Cheshire Cat's conversation with Alice about madness.

**msg 9** — The grin is the very last part of the Cheshire Cat to fade away. The context states that the Cat vanished "quite slowly, beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone."

**msg 10** — Yes, the Cheshire Cat reappears during the croquet game. Alice notices "a curious appearance in the air" which she makes out to be a grin, and then the Cat's head appears gradually — first the grin, then the eyes, then the whole head — and he speaks with Alice about the game.

**msg 11** — The argument arose during the croquet game when the executioner, the King, and the Queen were disputing whether the Cheshire Cat could be beheaded. The executioner argued that you couldn't cut off a head unless there was a body to cut it off from, and that he had never done such a thing before. The King argued that anything with a head could be beheaded, while the Queen insisted that if something wasn't done quickly she would have everybody executed.

**msg 12** — Based on the provided context, nothing has been established about the Cheshire Cat. The retrieved fragments cover Chapters III, IV, and VI of *Alice's Adventures in Wonderland*, but none of these chapters contain any mention or description of the Cheshire Cat. The Cat first appears in Chapter VI ("Pig and Pepper") after the fragments provided here, and the other chapters retrieved do not reference it.

**msg 13** — The first time Alice spots the Cheshire Cat in the kitchen scene, he is sitting on the hearth and grinning from ear to ear. The context states: "the only things in the kitchen that did not sneeze, were the cook, and a large cat which was sitting on the hearth and grinning from ear to ear."

</details>

## Scenario: Trial of the Knave — fixed terms + interim conclusions

- **Q1 — loses the goal by message 12?** NO (goal retained ✅)
  - goals in TaskState at message 12: `['Work through the trial of the Knave of Hearts', 'Summarize the trial so far, including the interim conclusions']`
- **Q2 — keeps emitting Sources + Quotes?** YES ✅ (13/13 non-refusal answers had both blocks; 0 refusal(s))

| # | User message | Rewritten query | Refusal? | Quotes | Sources | Goals in TaskState |
|---|---|---|---|---|---|---|
| 1 | Let's carefully work through the trial of the Knave of Hearts. Who is on trial, and what is the charge? | trial of the Knave of Hearts charge | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge |
| 2 | Let's fix a term: from now on, whenever I say 'the accused', I mean the Knave of Hearts. Acknowledge and use it. | Who is the Knave of Hearts on trial for, and what is the charge against the Knave of Hearts? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge |
| 3 | Who presides as the judge at this trial? | Who presides as the judge at the trial of the Knave of Hearts? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge |
| 4 | Fix another term: 'the poem' = the verses read out as evidence. What does the White Rabbit read out? | What does the White Rabbit read out as evidence in the trial of the Knave of Hearts? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out |
| 5 | Who was the first witness called to give evidence? | Who was the first witness called to give evidence at the trial of the Knave of Hearts? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence |
| 6 | What did the Hatter say and do while he was being questioned? | What did the Hatter say and do while the Hatter was being questioned at the trial? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning |
| 7 | Interim conclusion to note: the evidence so far is chaotic and nonsensical. Based on the text, is that fair? | Based on the text, is it fair to say the evidence at the trial is chaotic and nonsensical? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning; Assess whether the evidence so far is chaotic and nonsensical |
| 8 | Who was the next witness after the Hatter? | Who was the next witness after the Hatter in the trial? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning; Assess whether the evidence so far is chaotic and nonsensical; Identify the next witness after the Hatter |
| 9 | What was the King's rule about the 'most important' piece of evidence? | What was the King of Hearts' rule about the most important piece of evidence? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning; Assess whether the evidence so far is chaotic and nonsensical; Identify the next witness after the Hatter |
| 10 | What did Alice start to notice was happening to her own size during the trial? | What did Alice notice about her own size changing during the trial? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning; Assess whether the evidence so far is chaotic and nonsensical; Identify the next witness after the Hatter |
| 11 | Using our fixed term, remind me: what is 'the accused' charged with? | What is the Knave of Hearts charged with? | no | yes | yes | Work through the trial of the Knave of Hearts; Identify who is on trial and the charge; Determine who presides as the judge; Find out what the White Rabbit reads out; Identify the first witness called to give evidence; Describe the Hatter's testimony and actions during questioning; Assess whether the evidence so far is chaotic and nonsensical; Identify the next witness after the Hatter |
| 12 | Summarize the trial so far, including the interim conclusions we fixed. | Summarize the trial of the Knave of Hearts so far, including the interim conclusions about the evidence and the King's rule about the most important piece of evidence. | no | yes | yes | Work through the trial of the Knave of Hearts; Summarize the trial so far, including the interim conclusions |
| 13 | Finally: how does Alice bring the whole trial to a chaotic end? | How does Alice bring the trial to a chaotic end? | no | yes | yes | Work through the trial of the Knave of Hearts; Summarize the trial so far, including the interim conclusions; Explain how Alice brings the trial to a chaotic end |

Final TaskState: `{'goals': ['Work through the trial of the Knave of Hearts', 'Summarize the trial so far, including the interim conclusions', 'Explain how Alice brings the trial to a chaotic end'], 'constraints_and_terms': ["'the accused' = the Knave of Hearts", "'the poem' = the verses read out as evidence"], 'user_clarifications': ['Interim conclusion: the evidence so far is chaotic and nonsensical']}`

<details><summary>Answer bodies (for auditing the constraint check)</summary>

**msg 1** — The Knave of Hearts is on trial, and the charge is that he stole the tarts made by the Queen of Hearts.

**msg 2** — Acknowledged. From now on, whenever you say 'the accused', I will understand that you mean the Knave of Hearts, and I will use that term accordingly in my answers.

**msg 3** — The King of Hearts presides as the judge at the trial.

**msg 4** — The White Rabbit reads out 'the poem' — the verses that begin with "They told me you had been to her, / And mentioned me to him" and continue through several stanzas about giving and returning items, swimming, and a secret between two parties.

**msg 5** — The first witness called to give evidence was the Hatter.

**msg 6** — While being questioned, the Hatter gave confused and evasive testimony, repeatedly claiming he was "a poor man," mentioning his tea and bread-and-butter, and referring to the March Hare and Dormouse. He trembled, shifted from foot to foot, bit a piece out of his teacup instead of his bread-and-butter, and eventually dropped his teacup and bread-and-butter and went down on one knee. The King threatened him with execution multiple times for not giving clear answers.

**msg 7** — Yes, that is a fair assessment. The evidence so far is chaotic and nonsensical: the Hatter gave confused, evasive testimony about tea and bread-and-butter while trembling and biting his teacup; the King repeatedly threatened execution for trivial reasons; the jury wrote down three different dates and added them up as shillings and pence; the cook refused to give evidence and answered "Pepper, mostly" when asked what tarts are made of; and the Dormouse was suppressed for saying "Treacle." The proceedings are marked by absurd interruptions, arbitrary threats, and a complete lack of coherent or relevant evidence.

**msg 8** — The next witness after the Hatter was the Duchess's cook.

**msg 9** — The King's rule about the "most important" piece of evidence was that if there was no meaning in it, that saved a world of trouble, as they needn't try to find any. However, he then contradicted himself by saying he seemed to see some meaning in the verses after all.

**msg 10** — During the trial, Alice began to notice that she was growing larger again. She felt a "very curious sensation" and realized she was "beginning to grow larger again," and she thought at first she would get up and leave the court, but decided to remain as long as there was room for her.

**msg 11** — Based on the context, 'the accused' (the Knave of Hearts) is charged with stealing the tarts that the Queen of Hearts made. The accusation, read aloud by the White Rabbit, states: "The Queen of Hearts, she made some tarts, / All on a summer day: / The Knave of Hearts, he stole those tarts, / And took them quite away!"

**msg 12** — The trial so far has been chaotic and nonsensical. It began with the accusation that the Knave of Hearts stole the Queen's tarts, read by the White Rabbit. The first witness, the Hatter, gave confused testimony about tea and was dismissed (with the Queen ordering his head cut off, though he escaped). The next witness, the Duchess's cook, refused to give evidence and only said tarts are made of "Pepper, mostly" before disappearing during the commotion of suppressing the Dormouse. The interim conclusion we fixed is that the evidence so far is chaotic and nonsensical.

**msg 13** — Alice brings the trial to a chaotic end by growing to her full size, defying the King's invented "Rule Forty-two" about leaving the court, and then directly challenging the nonsense of the proceedings. When the King orders the jury to "Consider your verdict," Alice interrupts, declaring "Who cares for you? You're nothing but a pack of cards!" At this, the entire pack of cards rises up into the air and comes flying down upon her, causing her to wake up from her dream.

</details>

