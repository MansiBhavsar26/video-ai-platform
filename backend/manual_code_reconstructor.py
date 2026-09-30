from app.services.code_reconstructor import (
    reconstruct_code,
)


frame_results = [
    {
        "timestamp": 1888.87,
        "code": """
import $ from 'jquery';
import React, { Component } from 'react';
import MyComponent from './MyComponent';
import './App.css';

class App extends Component {
constructor(props) {
super(props);
this.state = {
data: []
};
"""
    },
    {
        "timestamp": 1892.84,
        "code": """
class App extends Component {
constructor(props) {
super(props);
this.state = {
data: []
};
componentWillMount() {
$.ajax({
context: this,
method: 'GET',
"""
    },
    {
        "timestamp": 1898.80,
        "code": """
this.state = {
data: []
};
componentWillMount() {
$.ajax({
context: this,
method: 'GET',
url: '/'
success(response) {
this.setState({ data: response.data })
"""
    },
]


result = reconstruct_code(
    frame_results
)


print()
print("=" * 70)
print("ORDERED CODE RECONSTRUCTION TEST")
print("=" * 70)

print()
print("RECONSTRUCTED CODE:")
print("-" * 70)

print(
    result["code"]
)

print()
print("-" * 70)

print(
    "TOTAL RECONSTRUCTED LINES:",
    len(result["lines"]),
)

print()
print("LINE DETAILS:")
print("-" * 70)

for index, line in enumerate(
    result["lines"],
    start=1,
):

    print(
        f"{index:02d} | "
        f"confidence={line['confidence']:.3f} | "
        f"observations={line['observations']} | "
        f"{line['text']}"
    )

print()
print("=" * 70)