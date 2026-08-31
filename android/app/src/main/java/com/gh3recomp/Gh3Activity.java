package com.gh3recomp;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.widget.Toast;

import org.libsdl.app.SDLActivity;

/**
 * Guitar Hero III: Legends of Rock (recompilado) -- activity Android.
 *
 * Carrega o runtime nativo (que liga o SDL3 estaticamente e fornece a cola JNI
 * do SDL) e a seguir a biblioteca do jogo recompilado. A ULTIMA entrada e o
 * "main shared object": e nela que o SDL procura SDL_main(), que o nosso
 * src/main_android.cpp define para ir buscar e correr a app registada sob "gh3".
 *
 * Os dados do jogo (3,9 GB) vivem em /sdcard/gh3/game e sao lidos diretamente
 * dessa pasta publica -- e a unica onde o utilizador os consegue por sem root,
 * seja por "adb push" ou por um gestor de ficheiros. Ler de la exige:
 *   - Android 11+ : "Acesso a todos os ficheiros" (MANAGE_EXTERNAL_STORAGE)
 *   - Android 10 e anteriores : READ_EXTERNAL_STORAGE em tempo de execucao
 * O arranque fica bloqueado nessa permissao para o jogo nunca abrir sem dados
 * (sem ela o sintoma seria um ecra preto sem explicacao nenhuma).
 */
public class Gh3Activity extends SDLActivity {
    private static final int REQUEST_STORAGE = 1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (!Environment.isExternalStorageManager()) {
                Toast.makeText(this,
                        "Conceda 'Acesso a todos os ficheiros' ao Guitar Hero 3 e reabra a app.",
                        Toast.LENGTH_LONG).show();
                try {
                    Intent intent = new Intent(
                            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                            Uri.parse("package:" + getPackageName()));
                    startActivity(intent);
                } catch (Exception e) {
                    startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
                }
                finish();
                return;
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            // Android 6..10: nao existe MANAGE_EXTERNAL_STORAGE, a permissao
            // classica de leitura chega para /sdcard/gh3. Pedimo-la e deixamos
            // o super.onCreate seguir -- se for negada, o codigo nativo nao
            // encontra o default.xex e diz-se isso no log.
            if (checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(
                        new String[]{Manifest.permission.READ_EXTERNAL_STORAGE},
                        REQUEST_STORAGE);
            }
        }
        super.onCreate(savedInstanceState);
    }

    @Override
    protected String[] getLibraries() {
        return new String[]{
            "rexruntimerd", // runtime + SDL3 (build RelWithDebInfo -> sufixo "rd")
            "gh3",          // jogo recompilado; exporta SDL_main
        };
    }
}
