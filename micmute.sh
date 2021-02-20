#!/bin/sh
if amixer get Digital | grep -Fq "Capture 0 ["; then
	amixer set Digital 61
	amixer set Capture 51
else
	amixer set Digital 0
	amixer set Capture 0
fi
