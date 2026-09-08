from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
@dataclass(frozen=True)
class GenerationResult:
    provider:str
    model:str
    text:str
    input_chars:int
    output_chars:int
class AIProvider(Protocol):
    provider_name:str
    model:str
    def generate_text(self,prompt:str,*,max_output_tokens:int=120)->GenerationResult: ...
