import {ChangeEvent, useState} from 'react';
import "../App.css"
import {uploadStatus} from "../types/types";
import {pyProject, sourceFile} from "../types/types";

export interface startButtonProperties{
    //Keeps track of the currently uploaded pyProject object
    project : pyProject | null;
}

export default function StartButton(){
    return(
        <>
            <div className="headingCenter">
                <button className="startButton">
                    <img src="./StartButton.png" alt="Start Button"/>
                </button>
            </div>
        </>
    );
}
