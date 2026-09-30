from app.services.code_ocr_normalizer import (
    normalize_code_ocr,
)


ocr_text = """
import React, { Component } from ‘react’;
import MyComponent from './MyComponent';
import './App.css';

class App extends Conjponent {
constructor(props)’{
super(props);

this.state = {
data: ‘'
};

componentWiltmMount() {
$.ajax({
context: this,
method: ‘GET’,
url: '/'
success(respanse) {
this.setState({ data: response.data })
}.bind(this)
})
}
"""


print()
print("=" * 70)
print("CODE OCR NORMALIZATION")
print("=" * 70)

print()
print("RAW OCR:")
print("-" * 70)
print(ocr_text)

normalized = normalize_code_ocr(
    ocr_text
)

print()
print("NORMALIZED CODE:")
print("-" * 70)
print(normalized)

print()
print("=" * 70)