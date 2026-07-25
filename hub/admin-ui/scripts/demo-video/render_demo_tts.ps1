param(
    [Parameter(Mandatory = $true)]
    [string]$SpecPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$spec = Get-Content -LiteralPath $SpecPath -Raw -Encoding UTF8 | ConvertFrom-Json
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice([string]$spec.voice)

try {
    foreach ($line in $spec.lines) {
        $escaped = [System.Security.SecurityElement]::Escape([string]$line.spoken_text)
        $rate = [int]$spec.rate_percent
        $rateValue = if ($rate -ge 0) { "+$rate%" } else { "$rate%" }
        $volume = [int]$spec.volume_percent
        $language = [string]$spec.ssml_language
        $ssml = @"
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="$language">
  <voice name="$($spec.voice)">
    <prosody rate="$rateValue" volume="$volume%">$escaped</prosody>
  </voice>
</speak>
"@
        $outputPath = Join-Path $OutputDirectory ("{0}.wav" -f $line.id)
        $synth.SetOutputToWaveFile($outputPath)
        $synth.SpeakSsml($ssml)
        $synth.SetOutputToNull()
        Write-Output $outputPath
    }
}
finally {
    $synth.Dispose()
}
