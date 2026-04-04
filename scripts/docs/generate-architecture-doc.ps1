param(
    [string]$MarkdownPath = "d:\PycharmProjects\carebank-backend\ARCHITECTURE_TEMPLATE.md",
    [string]$ReferenceDocPath = "d:\PycharmProjects\carebank-backend\refrence.doc",
    [string]$OutputDocxPath = "d:\PycharmProjects\carebank-backend\CareBank_Architecture.docx",
    [string]$DiagramScriptPath = "d:\PycharmProjects\carebank-backend\scripts\generate_architecture_svgs.py",
    [string]$DiagramDir = "d:\PycharmProjects\carebank-backend\docs\architecture-diagrams"
)

$ErrorActionPreference = 'Stop'

function Get-NextNonEmptyLine {
    param(
        [string[]]$Lines,
        [int]$StartIndex
    )

    for ($i = $StartIndex; $i -lt $Lines.Count; $i++) {
        if (-not [string]::IsNullOrWhiteSpace($Lines[$i])) {
            return @{ Index = $i; Text = $Lines[$i].Trim() }
        }
    }

    return $null
}

function Parse-MarkdownDocument {
    param([string[]]$Lines)

    $nonEmpty = @()
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if (-not [string]::IsNullOrWhiteSpace($Lines[$i])) {
            $nonEmpty += @{ Index = $i; Text = $Lines[$i].Trim() }
        }
    }

    if ($nonEmpty.Count -lt 2) {
        throw "Unable to determine title from markdown."
    }

    $titleLine1 = $nonEmpty[0].Text
    $titleLine2 = $nonEmpty[1].Text

    $revisionDate = ''
    $revisionVersion = ''
    $revisionDescription = ''
    $revisionAuthor = ''

    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq 'Document Revisions') {
            $entry = Get-NextNonEmptyLine -Lines $Lines -StartIndex ($i + 2)
            if ($entry) {
                $parts = ($entry.Text -replace '\s{2,}', '|').Split('|')
                if ($parts.Count -ge 4) {
                    $revisionDate = $parts[0].Trim()
                    $revisionVersion = $parts[1].Trim()
                    $revisionDescription = $parts[2].Trim()
                    $revisionAuthor = $parts[3].Trim()
                }
            }
        }
    }

    $approvalText = 'Virtusa Corporation and Client have reviewed this document and hereby agree that the contents herein are accurate. Any changes to this document must be communicated in writing and signed-off by both parties.'
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -eq 'Document Approval') {
            $entry = Get-NextNonEmptyLine -Lines $Lines -StartIndex ($i + 1)
            if ($entry) {
                $approvalText = $entry.Text
            }
        }
    }

    $bodyStart = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -cmatch '^1\s+Introduction$') {
            $bodyStart = $i
            break
        }
    }

    if ($bodyStart -lt 0) {
        throw "Unable to find the start of the body section."
    }

    $tokens = New-Object System.Collections.Generic.List[object]
    $paragraphBuffer = New-Object System.Collections.Generic.List[string]

    function Flush-ParagraphBuffer {
        if ($paragraphBuffer.Count -gt 0) {
            $text = ($paragraphBuffer -join ' ').Trim()
            if ($text) {
                $tokens.Add([pscustomobject]@{
                    Type = 'Paragraph'
                    Text = $text
                })
            }
            $paragraphBuffer.Clear()
        }
    }

    for ($i = $bodyStart; $i -lt $Lines.Count; $i++) {
        $line = $Lines[$i].TrimEnd()
        $trimmed = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            Flush-ParagraphBuffer
            continue
        }

        if ($trimmed -eq 'APPENDIX') {
            Flush-ParagraphBuffer
            $tokens.Add([pscustomobject]@{
                Type = 'Heading1'
                Text = 'Appendix'
            })
            continue
        }

        if ($trimmed -match '^(\d+)\s+(.+)$') {
            Flush-ParagraphBuffer
            $tokens.Add([pscustomobject]@{
                Type = 'Heading1'
                Text = ($matches[1].Trim() + ' ' + $matches[2].Trim())
            })
            continue
        }

        if ($trimmed -match '^(\d+\.\d+)\s+(.+)$') {
            Flush-ParagraphBuffer
            $tokens.Add([pscustomobject]@{
                Type = 'Heading2'
                Text = ($matches[1].Trim() + ' ' + $matches[2].Trim())
            })
            continue
        }

        if ($trimmed -match '^(\d+\.)\s+(.+)$') {
            Flush-ParagraphBuffer
            $tokens.Add([pscustomobject]@{
                Type = 'Heading2'
                Text = ($matches[1].Trim() + ' ' + $matches[2].Trim())
            })
            continue
        }

        if ($trimmed -match '^- (.+)$') {
            Flush-ParagraphBuffer
            $tokens.Add([pscustomobject]@{
                Type = 'Bullet'
                Text = $matches[1].Trim()
            })
            continue
        }

        $paragraphBuffer.Add($trimmed)
    }

    Flush-ParagraphBuffer

    return [pscustomobject]@{
        TitleLine1 = $titleLine1
        TitleLine2 = $titleLine2
        RevisionDate = $revisionDate
        RevisionVersion = $revisionVersion
        RevisionDescription = $revisionDescription
        RevisionAuthor = $revisionAuthor
        ApprovalText = $approvalText
        Tokens = $tokens
    }
}

function Set-ParagraphText {
    param(
        $Document,
        [int]$ParagraphIndex,
        [string]$Text
    )

    if ($ParagraphIndex -le $Document.Paragraphs.Count) {
        $Document.Paragraphs.Item($ParagraphIndex).Range.Text = "$Text`r"
    }
}

function Clear-TableDataRows {
    param(
        $Table,
        [int]$FromRow
    )

    for ($row = $FromRow; $row -le $Table.Rows.Count; $row++) {
        for ($col = 1; $col -le $Table.Columns.Count; $col++) {
            try {
                $Table.Cell($row, $col).Range.Text = "`r"
            } catch {
            }
        }
    }
}

function Add-StyledParagraph {
    param(
        $Selection,
        $Document,
        [string]$StyleName,
        [string]$Text,
        [int]$OutlineLevel
    )

    $start = $Selection.Start
    $Selection.Style = $Document.Styles.Item($StyleName)
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()

    $paragraphRange = $Document.Range($start, $Selection.Start - 1)
    $paragraphRange.Style = $Document.Styles.Item($StyleName)
    try {
        $paragraphRange.ListFormat.RemoveNumbers()
    } catch {
    }
    try {
        $paragraphRange.ParagraphFormat.OutlineLevel = $OutlineLevel
    } catch {
    }
}

function Find-ParagraphIndexByText {
    param(
        $Document,
        [string]$Text
    )

    for ($i = 1; $i -le $Document.Paragraphs.Count; $i++) {
        $current = $Document.Paragraphs.Item($i).Range.Text.Replace("`r", ' ').Replace([char]7, ' ').Trim()
        if ($current -eq $Text) {
            return $i
        }
    }

    return $null
}

function Insert-DiagramAfterHeading {
    param(
        $Document,
        [string]$HeadingText,
        [string]$CaptionText,
        [string]$ImagePath,
        [float]$WidthPoints = 430
    )

    if (-not (Test-Path -LiteralPath $ImagePath)) {
        return
    }

    $headingIndex = Find-ParagraphIndexByText -Document $Document -Text $HeadingText
    if (-not $headingIndex) {
        return
    }

    $insertAt = $Document.Paragraphs.Item($headingIndex).Range.End
    $range = $Document.Range($insertAt, $insertAt)
    $range.InsertParagraphAfter() | Out-Null
    $range.Collapse(0)
    $range.InsertAfter($CaptionText)
    $range.ParagraphFormat.Alignment = 1
    $range.Font.Bold = $true
    $range.Font.Size = 10
    $range.InsertParagraphAfter() | Out-Null

    $imageRange = $Document.Range($range.End, $range.End)
    $imageRange.InlineShapes.AddPicture($ImagePath) | Out-Null
    $shape = $Document.InlineShapes.Item($Document.InlineShapes.Count)
    $shape.LockAspectRatio = -1
    $shape.Width = $WidthPoints
    $shape.Range.ParagraphFormat.Alignment = 1
    $afterRange = $Document.Range($shape.Range.End, $shape.Range.End)
    $afterRange.InsertParagraphAfter() | Out-Null
}

$content = Get-Content -LiteralPath $MarkdownPath
$parsed = Parse-MarkdownDocument -Lines $content

if (Test-Path -LiteralPath $DiagramScriptPath) {
    & python $DiagramScriptPath
}

$wdPageBreak = 7
$wdFormatDocumentDefault = 16

$word = $null
$doc = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0

    Remove-Item -LiteralPath $OutputDocxPath -ErrorAction SilentlyContinue
    $doc = $word.Documents.Open($ReferenceDocPath, $false, $true)

    Set-ParagraphText -Document $doc -ParagraphIndex 13 -Text $parsed.TitleLine1
    Set-ParagraphText -Document $doc -ParagraphIndex 14 -Text $parsed.TitleLine2
    Set-ParagraphText -Document $doc -ParagraphIndex 17 -Text ''
    Set-ParagraphText -Document $doc -ParagraphIndex 18 -Text ''
    Set-ParagraphText -Document $doc -ParagraphIndex 88 -Text $parsed.ApprovalText

    $revisionTable = $doc.Tables.Item(1)
    if ($revisionTable.Rows.Count -lt 2) {
        $revisionTable.Rows.Add() | Out-Null
    }
    $revisionTable.Cell(2, 1).Range.Text = $parsed.RevisionDate
    $revisionTable.Cell(2, 2).Range.Text = $parsed.RevisionVersion
    $revisionTable.Cell(2, 3).Range.Text = $parsed.RevisionDescription
    $revisionTable.Cell(2, 4).Range.Text = $parsed.RevisionAuthor
    if ($revisionTable.Rows.Count -gt 2) {
        Clear-TableDataRows -Table $revisionTable -FromRow 3
    }

    $approvalTable = $doc.Tables.Item(2)
    $approvalTable.Cell(4, 1).Range.Text = 'Client: CareBank'
    $approvalTable.Cell(4, 2).Range.Text = 'Virtusa Corporation'

    $startDelete = $doc.Paragraphs.Item(103).Range.Start
    $endDelete = $doc.Content.End - 1
    $doc.Range($startDelete, $endDelete).Delete()

    $insertRange = $doc.Range($doc.Content.End - 1, $doc.Content.End - 1)
    $insertRange.InsertBreak($wdPageBreak)

    $selection = $word.Selection
    $selection.SetRange($doc.Content.End - 1, $doc.Content.End - 1)

    foreach ($token in $parsed.Tokens) {
        switch ($token.Type) {
            'Heading1' {
                Add-StyledParagraph -Selection $selection -Document $doc -StyleName 'Heading 1,l1' -Text $token.Text -OutlineLevel 1
            }
            'Heading2' {
                Add-StyledParagraph -Selection $selection -Document $doc -StyleName 'Heading 2,1.1' -Text $token.Text -OutlineLevel 2
            }
            'Bullet' {
                $selection.Style = $doc.Styles.Item('Body Text 2')
                $selection.TypeText('- ' + $token.Text)
                $selection.TypeParagraph()
            }
            default {
                $selection.Style = $doc.Styles.Item('Body Text 2')
                $selection.TypeText($token.Text)
                $selection.TypeParagraph()
            }
        }
    }

    Insert-DiagramAfterHeading -Document $doc -HeadingText '4.1 Overview' -CaptionText 'Figure 1. Overall system architecture' -ImagePath (Join-Path $DiagramDir '01-overall-system.png') -WidthPoints 470
    Insert-DiagramAfterHeading -Document $doc -HeadingText '4.2 Logical/Functional View' -CaptionText 'Figure 2. Frontend architecture' -ImagePath (Join-Path $DiagramDir '03-frontend-architecture.png') -WidthPoints 450
    Insert-DiagramAfterHeading -Document $doc -HeadingText '4.4 Implementation/System View' -CaptionText 'Figure 3. Backend architecture' -ImagePath (Join-Path $DiagramDir '02-backend-architecture.png') -WidthPoints 470
    Insert-DiagramAfterHeading -Document $doc -HeadingText '4.6 Deployment View' -CaptionText 'Figure 4. MockBank architecture' -ImagePath (Join-Path $DiagramDir '04-mockbank-architecture.png') -WidthPoints 460
    Insert-DiagramAfterHeading -Document $doc -HeadingText '4.5 Process/Thread View' -CaptionText 'Figure 5. End-to-end operational flow' -ImagePath (Join-Path $DiagramDir '05-operational-flow.png') -WidthPoints 500

    if ($doc.TablesOfContents.Count -gt 0) {
        $doc.TablesOfContents.Item(1).Update()
    }
    $doc.Fields.Update() | Out-Null

    $doc.SaveAs([ref]$OutputDocxPath, [ref]$wdFormatDocumentDefault)
    $doc.Close()
    $word.Quit()
} finally {
    if ($doc -ne $null) {
        try { $doc.Close([ref]$false) } catch {}
    }
    if ($word -ne $null) {
        try { $word.Quit() } catch {}
    }
}

Write-Output "Created:"
Write-Output $OutputDocxPath
